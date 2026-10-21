# SDS-20: node hand-back

- mineru: `{"mineru_version":"4.0.12","python_version":"3.12.3"}`
- GPU / driver: NVIDIA A100-SXM4-80GB, 580.178.04
- CUDA (driver): CUDA Version: 13.0; PyTorch build cu130, vLLM 0.28.0
- OS: Ubuntu 24.04.5 LTS
- engine: vllm-async-engine (both passes), tier standard; page pass with --ocr-mode ocr

## Page pass
- 13:55 SDS-20 ok 191s; last inference window pages=287 speed=2.183 page/s

## Crop pass
- 16:55 SDS-20-crops ok 576s (one `mineru-kit parse <dir>` process, one engine; crops are parsed one image at a time, so no batching across crops)

```
crops in manifest: 360  |  with <table>: 249  |  text only: 111  |  no output found: 0
n_lines - <tr> distribution: -7:1 1:9 2:8 3:5 4:4 5:11 6:3 7:9 8:4 9:2 10:6 11:9 12:7 13:9 14:4 15:4 16:10 17:7 18:5 19:8 20:10 21:9 22:3 23:5 24:7 25:10 26:12 27:3 28:13 29:1 30:5 31:2 32:2 33:3 34:6 35:11 36:7 37:2 39:2 43:3 44:1 45:1 46:1 47:1 50:1 55:1 57:1 58:1
within tolerance (-3..+4): 26 of 249 tables (10 %)
outside tolerance (crop, n_lines, <tr>): p009_0 60/3, p009_1 45/2, p011_0 58/8, p015_0 33/7, p018_0 14/2, p020_0 11/2, p022_1 20/5, p022_2 19/5, p022_3 16/4, p022_4 14/3, p024_0 27/8, p025_0 45/2, p030_0 23/12, p033_0 40/20, p034_1 45/26, p035_1 44/19, p036_1 51/29, p037_0 34/2, p038_1 20/8, p039_0 32/2, p042_1 20/8, p043_0 33/7, p044_0 33/3, p045_0 27/7, p046_0 33/2, p047_0 30/7, p049_1 20/8, p050_0 32/2, p051_0 27/7, p054_0 13/8, p055_0 34/2, p056_1 20/8, p057_0 36/2, p058_1 21/8, p059_0 30/7, p061_0 27/8, p064_1 21/8, p065_0 37/2, p071_0 37/2, p071_1 30/2 …
text only: p007_0, p007_1, p007_2, p007_3, p007_4, p008_0, p008_1, p008_3, p008_4, p008_5, p009_2, p009_3, p010_0, p012_0, p013_0, p014_0, p016_0, p017_0, p019_0, p021_0, p022_0, p025_1, p026_1, p031_0, p031_1, p032_1, p036_0, p037_1, p039_1, p041_0, p044_1, p047_1, p048_0, p050_1, p051_1, p055_1, p059_1, p060_0, p062_2, p063_0 …

--- p041_0 verbatim ---
(no table found)
```
