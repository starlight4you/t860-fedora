/* SPDX-License-Identifier: GPL-2.0-only */
#define _FILE_OFFSET_BITS 64
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint64_t be64(const unsigned char *p) {
    uint64_t n = 0;
    for (int i=0; i<8; i++) n=(n<<8)|p[i];
    return n;
}
static uint32_t le32(const unsigned char *p) {
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static int contains(const unsigned char *b, size_t size, const char *s) {
    size_t n=strlen(s);
    for (size_t i=0; i+n<=size; i++) if (!memcmp(b+i,s,n)) return 1;
    return 0;
}
int main(int argc, char **argv) {
    FILE *f;
    unsigned char *b;
    long size;
    if (argc!=3 || (strcmp(argv[2],"stock") && strcmp(argv[2],"uefi")) ||
        !(f=fopen(argv[1],"rb"))) return 1;
    if (fseek(f,0,SEEK_END) || (size=ftell(f))!=67108864 || fseek(f,0,SEEK_SET)) return 2;
    b=malloc((size_t)size);
    if (!b || fread(b,1,(size_t)size,f)!=(size_t)size) return 3;
    fclose(f);
    unsigned char *footer=b+size-64;
    uint64_t offset=be64(footer+20), len=be64(footer+28);
    int ok=!memcmp(b,"ANDROID!",8) && le32(b+36)==4096 && le32(b+40)==1 &&
        !memcmp(footer,"AVBf",4) && offset<(uint64_t)size-64 && len>=256 &&
        len<=(uint64_t)size-64-offset && !memcmp(b+offset,"AVB0",4) &&
        contains(b+4096,128,"UNCOMPRESSED_IMG") && contains(b,(size_t)size,"SEANDROIDENFORCE");
    if (!strcmp(argv[2],"uefi")) ok &= contains(b,(size_t)size,"_FVH");
    else ok &= !contains(b,(size_t)size,"_FVH");
    free(b);
    puts(ok ? "Samsung boot structure verified" : "Unsupported or corrupt Samsung boot image");
    return ok ? 0 : 4;
}
