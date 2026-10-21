# SDS-57: node hand-back

- mineru: `{"mineru_version":"4.0.12","python_version":"3.12.3"}`
- GPU / driver: NVIDIA A100-SXM4-80GB, 580.178.04
- CUDA (driver): CUDA Version: 13.0; PyTorch build cu130, vLLM 0.28.0
- OS: Ubuntu 24.04.5 LTS
- engine: vllm-async-engine (both passes), tier standard; page pass with --ocr-mode ocr

## Page pass
- 13:47 SDS-57 ok 258s; last inference window pages=375 speed=2.010 page/s

## Crop pass
- 16:19 SDS-57-crops ok 612s (one `mineru-kit parse <dir>` process, one engine; crops are parsed one image at a time, so no batching across crops)

```
crops in manifest: 333  |  with <table>: 268  |  text only: 65  |  no output found: 0
n_lines - <tr> distribution: -2:1 0:2 1:8 2:26 3:15 4:17 5:15 6:13 7:20 8:16 9:12 10:7 11:14 12:7 13:5 14:2 15:3 16:6 17:3 18:2 19:3 20:11 21:2 22:10 23:3 24:5 25:9 26:4 27:3 28:3 29:2 30:2 31:2 32:2 37:1 38:1 42:3 43:1 47:1 49:1 54:1 55:1 56:2 57:1
within tolerance (-3..+4): 69 of 268 tables (26 %)
outside tolerance (crop, n_lines, <tr>): p007_0 58/2, p007_1 26/3, p007_2 11/3, p008_0 44/2, p008_1 32/4, p008_2 30/3, p008_3 28/3, p011_0 6/1, p015_0 28/5, p016_0 52/9, p018_0 51/13, p022_0 32/10, p023_1 12/3, p024_0 9/3, p025_0 28/8, p027_0 23/15, p033_0 11/2, p034_0 41/14, p035_0 47/22, p035_1 20/14, p036_0 21/16, p037_0 21/14, p038_0 15/10, p040_0 52/22, p043_0 47/24, p044_1 43/21, p045_1 17/12, p050_0 48/41, p051_0 60/54, p053_0 55/13, p055_0 61/4, p061_0 33/21, p063_0 36/14, p064_1 22/6, p065_0 18/6, p067_0 18/6, p069_0 36/25, p072_0 18/9, p073_0 17/9, p075_0 14/7 …
text only: p006_0, p012_0, p013_0, p014_0, p014_1, p017_0, p019_0, p031_0, p032_0, p041_0, p044_0, p045_0, p052_0, p054_0, p059_0, p062_0, p071_0, p074_0, p078_0, p080_0, p080_1, p081_0, p103_1, p113_0, p118_0, p142_1, p148_0, p154_1, p155_0, p156_1, p157_0, p160_0, p192_0, p195_0, p195_1, p196_0, p197_0, p198_0, p200_1, p204_0 …

--- p041_0 verbatim ---
(no table found)
```
