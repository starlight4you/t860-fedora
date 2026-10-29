// SPDX-License-Identifier: GPL-2.0-only
/*
 * Experimental Galaxy Tab S6 ANA38401 / AMSA05RB06 command-mode panel.
 * Timing and packet sequences come from Samsung's gts6lwifi r06 overlay.
 * Control commands go to DSI0 only; DSI1 carries the other half of the image.
 * Requires the MSM deferred-HS-clock patch: LP11 -> reset -> TCON-ready -> HS.
 */

#include <linux/delay.h>
#include <linux/gpio/consumer.h>
#include <linux/iopoll.h>
#include <linux/ktime.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/regulator/consumer.h>
#include <linux/workqueue.h>
#include <video/mipi_display.h>

#include <drm/drm_atomic.h>
#include <drm/drm_atomic_helper.h>
#include <drm/drm_bridge.h>
#include <drm/drm_connector.h>
#include <drm/drm_encoder.h>
#include <drm/drm_mipi_dsi.h>
#include <drm/drm_modes.h>
#include <drm/drm_vblank.h>

struct ana38401 {
	struct drm_bridge bridge;
	struct device *dev;
	struct work_struct display_on_work;
	struct drm_crtc_commit *first_commit;
	bool prepared;
	bool initialized;
	bool display_on_requested;
	ktime_t display_on_deadline;
	struct mipi_dsi_device *dsi;
	struct mipi_dsi_device *secondary;
	struct regulator_bulk_data supplies[3];
	struct gpio_desc *reset;
	struct gpio_desc *ready;
};

struct ana38401_cmd {
	u8 type;
	u8 len;
	u8 data[34];
};

/* Preserve the vendor packet types, including two-byte long writes. */
static const struct ana38401_cmd ana38401_init[] = {
	{ 0x15, 2, { 0xb0, 0x7f } },
	{ 0x39, 2, { 0xb2, 0x15 } },
	{ 0x15, 2, { 0xb0, 0xbc } },
	{ 0x39, 2, { 0xb2, 0x04 } },
	{ 0x39, 34, { 0x83, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80,
		      0x00, 0x80, 0x80, 0x00, 0x80, 0x80, 0x80, 0x80,
		      0x80, 0x80, 0x80, 0x00, 0x80, 0x80, 0x00, 0x80,
		      0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x00, 0x80,
		      0x80, 0x00 } },
	{ 0x39, 4, { 0x90, 0x00, 0x00, 0x0e } },
	{ 0x15, 2, { 0xb0, 0x67 } },
	{ 0x39, 2, { 0xb2, 0x0f } },
	{ 0x15, 2, { 0xb0, 0x4d } },
	{ 0x39, 2, { 0xb2, 0x04 } },
	{ 0x15, 2, { 0xb0, 0x49 } },
	{ 0x39, 2, { 0xb2, 0x99 } },
	{ 0x15, 2, { 0xb0, 0x36 } },
	{ 0x39, 2, { 0xb2, 0x10 } },
	{ 0x15, 2, { 0xb0, 0x35 } },
	{ 0x39, 2, { 0xb2, 0x01 } },
};

static struct ana38401 *to_ana38401(struct drm_bridge *bridge)
{
	return container_of(bridge, struct ana38401, bridge);
}

static int ana38401_write(struct ana38401 *ctx,
			 const struct ana38401_cmd *cmd)
{
	struct mipi_dsi_msg msg = {
		.channel = ctx->dsi->channel,
		.type = cmd->type,
		.tx_len = cmd->len,
		.tx_buf = cmd->data,
	};
	ssize_t ret;

	/* The generic DCS helper chooses short packets for two-byte payloads. */
	ret = ctx->dsi->host->ops->transfer(ctx->dsi->host, &msg);
	/* MSM reports its padded DMA packet length, including the header. */
	return ret < 0 ? ret : 0;
}

static int ana38401_prepare(struct ana38401 *ctx)
{
	int ret, ready;

	ret = regulator_bulk_enable(ARRAY_SIZE(ctx->supplies), ctx->supplies);
	if (ret)
		return ret;

	/* reset is active low in DT: logical 1 asserts the physical low. */
	gpiod_set_value_cansleep(ctx->reset, 1);
	msleep(70);
	gpiod_set_value_cansleep(ctx->reset, 0);
	ret = read_poll_timeout(gpiod_get_value_cansleep, ready, ready != 0,
				1000, 500000, false, ctx->ready);
	if (ret || ready < 0) {
		ret = ready < 0 ? ready : ret;
		dev_err(ctx->dev, "TCON-ready failed: %d\n", ret);
		gpiod_set_value_cansleep(ctx->reset, 1);
		regulator_bulk_disable(ARRAY_SIZE(ctx->supplies), ctx->supplies);
		return ret;
	}

	/* Samsung measures the 220ms minimum at display-on, not before init.
	 * Start HS and configure gamma/pixels as soon as the TCON is ready.
	 */
	ctx->display_on_deadline = ktime_add_ms(ktime_get(), 220);
	return 0;
}

static int ana38401_mtp_offset(u8 value)
{
	/* Factory offsets use sign/magnitude, not two's complement. */
	return value & 0x80 ? -(value & 0x7f) : value;
}

static int ana38401_calibrate_gamma(struct ana38401 *ctx)
{
	struct ana38401_cmd gamma = { 0x39, 34, { 0x83 } };
	u8 mtp[33], params[2] = { 0xd8, 0 };
	unsigned int offset, count, channel, i;
	ssize_t ret;
	int v255;

	/* Match Samsung's gpara reads: D8 at 0x5a, at most ten bytes each.
	 * ANA38401 requires the requested byte count as the second parameter.
	 */
	for (offset = 0; offset < sizeof(mtp); offset += count) {
		count = min_t(unsigned int, 10, sizeof(mtp) - offset);
		ret = mipi_dsi_dcs_write(ctx->dsi, 0xb0,
					(u8[]){ 0x5a + offset }, 1);
		if (ret < 0)
			return ret;
		params[1] = count;
		ret = mipi_dsi_generic_read(ctx->dsi, params, sizeof(params),
					   mtp + offset, count);
		if (ret != count)
			return ret < 0 ? ret : -EIO;
	}
	if (!memchr_inv(mtp, 0xff, sizeof(mtp)))
		return -ENODATA;

	/* Vendor gamma_cell_determine_max(): calibrated normal 360 cd/m2.
	 * Each channel contains V11..V203, V255 low, V3, V255 high/V0, VT.
	 * Lower brightness needs the vendor smart-dimming interpolation too.
	 */
	for (channel = 0; channel < 3; channel++) {
		u8 *dst = gamma.data + 1 + channel * 11;
		const u8 *src = mtp + channel * 11;

		for (i = 0; i < 7; i++)
			dst[i] = 128 + ana38401_mtp_offset(src[i]);
		v255 = 256 + (src[9] ? -src[7] : src[7]);
		dst[7] = v255 & 0xff;
		dst[8] = 128 + ana38401_mtp_offset(src[8]);
		dst[9] = v255 >= 256 ? 0x80 : 0;
		dst[10] = 0;
	}
	dev_info(ctx->dev, "factory MTP: %*ph\n", (int)sizeof(mtp), mtp);
	ret = ana38401_write(ctx, &gamma);
	if (ret)
		return ret;
	/* Latch the new gamma with the same vendor update command. */
	ret = ana38401_write(ctx, &(struct ana38401_cmd){ 0x15, 2, { 0xb0, 0x35 } });
	if (ret)
		return ret;
	return ana38401_write(ctx, &(struct ana38401_cmd){ 0x39, 2, { 0xb2, 0x01 } });
}

static int ana38401_enable(struct ana38401 *ctx)
{
	unsigned int i;
	int ret;

	/* MSM enables continuous HS clock after prepare and before this hook. */
	for (i = 0; i < ARRAY_SIZE(ana38401_init); i++) {
		ret = ana38401_write(ctx, &ana38401_init[i]);
		if (ret) {
			dev_err(ctx->dev, "initialization command %u failed: %d\n", i, ret);
			return ret;
		}
	}

	ret = ana38401_calibrate_gamma(ctx);
	if (ret) {
		dev_err(ctx->dev, "factory gamma calibration failed: %d\n", ret);
		return ret;
	}

	return 0;
}

static int ana38401_disable(struct ana38401 *ctx)
{
	int ret = mipi_dsi_dcs_set_display_off(ctx->dsi);

	msleep(100);
	return ret;
}

static int ana38401_unprepare(struct ana38401 *ctx)
{
	gpiod_set_value_cansleep(ctx->reset, 1);
	/* Vendor vddlcd supply pre-off delay, after display-off and reset. */
	usleep_range(5000, 6000);
	return regulator_bulk_disable(ARRAY_SIZE(ctx->supplies), ctx->supplies);
}

static const struct drm_display_mode ana38401_mode = {
	.clock = 299395,
	.hdisplay = 2560,
	.hsync_start = 2560 + 220,
	.hsync_end = 2560 + 220 + 84,
	.htotal = 2560 + 220 + 84 + 220,
	.vdisplay = 1600,
	.vsync_start = 1600 + 10,
	.vsync_end = 1600 + 10 + 2,
	.vtotal = 1600 + 10 + 2 + 6,
	.type = DRM_MODE_TYPE_DRIVER | DRM_MODE_TYPE_PREFERRED,
};

static int ana38401_get_modes(struct drm_bridge *bridge,
			      struct drm_connector *connector)
{
	struct drm_display_mode *mode;

	mode = drm_mode_duplicate(connector->dev, &ana38401_mode);
	if (!mode)
		return -ENOMEM;
	drm_mode_set_name(mode);
	drm_mode_probed_add(connector, mode);
	connector->display_info.width_mm = 227;
	connector->display_info.height_mm = 142;
	return 1;
}

/* Command-mode pixels are kicked off after bridge atomic_enable. Wait for
 * the first scan to finish on both bonded links before sending display-on.
 * Waiting in atomic_enable itself would deadlock that first kickoff.
 */
static void ana38401_display_on_work(struct work_struct *work)
{
	struct ana38401 *ctx = container_of(work, struct ana38401, display_on_work);
	struct drm_crtc_commit *commit = ctx->first_commit;
	struct drm_crtc *crtc = commit->crtc;
	s64 remaining_us;
	u64 count;
	int ret;

	if (!wait_for_completion_timeout(&commit->flip_done, msecs_to_jiffies(1000))) {
		dev_err(ctx->dev, "first frame timed out; keeping display off\n");
		goto out;
	}

	/* DPU can signal flip_done at CTL_START, before pixels start at TE.
	 * The first TE starts pixel DMA; the second closes that scan interval.
	 * One TE plus host-side DCS DMA arbitration only covers the primary
	 * link and can expose uninitialized RAM on the other bonded link.
	 */
	ret = drm_crtc_vblank_get(crtc);
	if (ret) {
		dev_err(ctx->dev, "cannot wait for first scan: %d\n", ret);
		goto out;
	}
	count = drm_crtc_vblank_count(crtc);
	ret = wait_event_timeout(*drm_crtc_vblank_waitqueue(crtc),
				drm_crtc_vblank_count(crtc) - count >= 2,
				msecs_to_jiffies(100));
	drm_crtc_vblank_put(crtc);
	if (!ret) {
		dev_err(ctx->dev, "first scan timed out; keeping display off\n");
		goto out;
	}

	remaining_us = ktime_us_delta(ctx->display_on_deadline, ktime_get());
	if (remaining_us > 0)
		usleep_range(remaining_us, remaining_us + 1000);
	if (!READ_ONCE(ctx->display_on_requested))
		goto out;

	ret = mipi_dsi_dcs_set_display_on(ctx->dsi);
	if (ret < 0)
		dev_err(ctx->dev, "display on failed: %d\n", ret);
	else
		dev_info(ctx->dev, "display on after first frame\n");
out:
	drm_crtc_commit_put(commit);
	ctx->first_commit = NULL;
}

static void ana38401_cancel_display_on(void *data)
{
	struct ana38401 *ctx = data;

	WRITE_ONCE(ctx->display_on_requested, false);
	cancel_work_sync(&ctx->display_on_work);
	/* A queued worker may have been cancelled before it took this reference. */
	if (ctx->first_commit) {
		drm_crtc_commit_put(ctx->first_commit);
		ctx->first_commit = NULL;
	}
}

static void ana38401_atomic_pre_enable(struct drm_bridge *bridge,
				      struct drm_atomic_state *state)
{
	struct ana38401 *ctx = to_ana38401(bridge);
	int ret = ana38401_prepare(ctx);

	ctx->prepared = !ret;
	if (ret)
		dev_err(ctx->dev, "prepare failed: %d\n", ret);
}

static void ana38401_atomic_enable(struct drm_bridge *bridge,
				  struct drm_atomic_state *state)
{
	struct ana38401 *ctx = to_ana38401(bridge);
	struct drm_crtc *crtc;
	struct drm_crtc_state *crtc_state;
	int ret;

	if (!ctx->prepared)
		return;
	crtc = drm_atomic_get_new_crtc_for_encoder(state, bridge->encoder);
	if (!crtc)
		return;
	crtc_state = drm_atomic_get_new_crtc_state(state, crtc);
	if (!crtc_state || !crtc_state->commit) {
		dev_err(ctx->dev, "missing first-frame commit\n");
		return;
	}

	ret = ana38401_enable(ctx);
	if (ret)
		return;
	ctx->initialized = true;
	WRITE_ONCE(ctx->display_on_requested, true);
	ctx->first_commit = drm_crtc_commit_get(crtc_state->commit);
	schedule_work(&ctx->display_on_work);
}

static void ana38401_atomic_disable(struct drm_bridge *bridge,
				   struct drm_atomic_state *state)
{
	struct ana38401 *ctx = to_ana38401(bridge);

	/* Finish/cancel the deferred DCS write before DSI or rails are disabled. */
	ana38401_cancel_display_on(ctx);
	if (ctx->initialized)
		ana38401_disable(ctx);
	ctx->initialized = false;
}

static void ana38401_atomic_post_disable(struct drm_bridge *bridge,
					struct drm_atomic_state *state)
{
	struct ana38401 *ctx = to_ana38401(bridge);

	if (ctx->prepared)
		ana38401_unprepare(ctx);
	ctx->prepared = false;
}

static const struct drm_bridge_funcs ana38401_bridge_funcs = {
	.atomic_pre_enable = ana38401_atomic_pre_enable,
	.atomic_enable = ana38401_atomic_enable,
	.atomic_disable = ana38401_atomic_disable,
	.atomic_post_disable = ana38401_atomic_post_disable,
	.get_modes = ana38401_get_modes,
	.atomic_reset = drm_atomic_helper_bridge_reset,
	.atomic_duplicate_state = drm_atomic_helper_bridge_duplicate_state,
	.atomic_destroy_state = drm_atomic_helper_bridge_destroy_state,
	.atomic_get_input_bus_fmts = drm_atomic_helper_bridge_propagate_bus_fmt,
};

static void ana38401_put_secondary(void *data)
{
	struct mipi_dsi_device *secondary = data;

	put_device(&secondary->dev);
}

static int ana38401_probe(struct mipi_dsi_device *dsi)
{
	struct device *dev = &dsi->dev;
	struct mipi_dsi_device *secondary;
	struct device_node *np;
	struct ana38401 *ctx;
	int ret;

	dsi->lanes = 4;
	dsi->format = MIPI_DSI_FMT_RGB888;
	dsi->mode_flags = 0; /* command mode, HS commands, continuous clock, EOT */
	if (of_device_is_compatible(dev->of_node,
				    "samsung,ana38401-amsa05rb06-secondary"))
		return devm_mipi_dsi_attach(dev, dsi);

	np = of_parse_phandle(dev->of_node, "link2", 0);
	if (!np)
		return dev_err_probe(dev, -EINVAL, "missing secondary DSI link\n");
	secondary = of_find_mipi_dsi_device_by_node(np);
	of_node_put(np);
	if (!secondary)
		return -EPROBE_DEFER;
	ret = devm_add_action_or_reset(dev, ana38401_put_secondary, secondary);
	if (ret)
		return ret;

	ctx = devm_drm_bridge_alloc(dev, struct ana38401, bridge,
				    &ana38401_bridge_funcs);
	if (IS_ERR(ctx))
		return PTR_ERR(ctx);
	ctx->dsi = dsi;
	ctx->secondary = secondary;
	ctx->dev = dev;
	INIT_WORK(&ctx->display_on_work, ana38401_display_on_work);
	ctx->bridge.of_node = dev->of_node;
	ctx->bridge.type = DRM_MODE_CONNECTOR_DSI;
	ctx->bridge.ops = DRM_BRIDGE_OP_MODES;
	ctx->bridge.pre_enable_prev_first = true;
	ctx->supplies[0].supply = "vddio";
	ctx->supplies[1].supply = "lab";
	ctx->supplies[2].supply = "ibb";
	ret = devm_regulator_bulk_get(dev, ARRAY_SIZE(ctx->supplies), ctx->supplies);
	if (ret)
		return dev_err_probe(dev, ret, "failed to get supplies\n");
	ctx->reset = devm_gpiod_get(dev, "reset", GPIOD_OUT_HIGH);
	if (IS_ERR(ctx->reset))
		return dev_err_probe(dev, PTR_ERR(ctx->reset), "failed to get reset\n");
	ctx->ready = devm_gpiod_get(dev, "tcon-rdy", GPIOD_IN);
	if (IS_ERR(ctx->ready))
		return dev_err_probe(dev, PTR_ERR(ctx->ready), "failed to get TCON-ready\n");
	mipi_dsi_set_drvdata(dsi, ctx);
	ret = devm_drm_bridge_add(dev, &ctx->bridge);
	if (ret)
		return ret;
	ret = devm_mipi_dsi_attach(dev, dsi);
	if (ret)
		return dev_err_probe(dev, ret, "DSI attach failed\n");
	return devm_add_action_or_reset(dev, ana38401_cancel_display_on, ctx);
}

static const struct of_device_id ana38401_of_match[] = {
	{ .compatible = "samsung,ana38401-amsa05rb06" },
	{ .compatible = "samsung,ana38401-amsa05rb06-secondary" },
	{ }
};
MODULE_DEVICE_TABLE(of, ana38401_of_match);

static struct mipi_dsi_driver ana38401_driver = {
	.probe = ana38401_probe,
	.driver = {
		.name = "panel-samsung-ana38401",
		.of_match_table = ana38401_of_match,
	},
};
module_mipi_dsi_driver(ana38401_driver);

MODULE_DESCRIPTION("Experimental Samsung ANA38401 AMSA05RB06 panel");
MODULE_LICENSE("GPL");
