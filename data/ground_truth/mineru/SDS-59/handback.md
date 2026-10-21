# SDS-59: node hand-back

- mineru: `{"mineru_version":"4.0.12","python_version":"3.12.3"}`
- GPU / driver: NVIDIA A100-SXM4-80GB, 580.178.04
- CUDA (driver): CUDA Version: 13.0; PyTorch build cu130, vLLM 0.28.0
- OS: Ubuntu 24.04.5 LTS
- engine: vllm-async-engine (both passes), tier standard; page pass with --ocr-mode ocr

## Page pass
- 13:43 SDS-59 ok 250s; last inference window pages=377 speed=2.108 page/s

## Crop pass
- 16:05 SDS-59-crops ok 719s (one `mineru-kit parse <dir>` process, one engine; crops are parsed one image at a time, so no batching across crops)

```
crops in manifest: 611  |  with <table>: 375  |  text only: 236  |  no output found: 0
n_lines - <tr> distribution: 0:96 1:57 2:19 3:4 4:24 5:36 6:16 7:12 8:44 9:4 10:12 11:5 12:2 13:7 14:4 15:6 16:1 18:1 19:1 20:2 21:1 26:2 27:1 28:3 29:2 30:2 34:1 35:2 37:3 38:3 43:1 59:1
within tolerance (-3..+4): 200 of 375 tables (53 %)
outside tolerance (crop, n_lines, <tr>): p009_0 61/2, p009_1 11/1, p010_0 34/4, p010_1 32/3, p014_0 17/5, p024_0 39/28, p024_1 39/28, p024_2 21/14, p024_3 20/14, p027_0 31/25, p028_0 45/37, p033_0 51/13, p051_1 7/2, p052_2 7/2, p053_2 8/2, p054_0 37/24, p054_2 7/2, p055_0 27/19, p055_1 7/2, p056_0 36/6, p056_2 7/2, p057_0 33/7, p057_2 7/2, p058_0 37/8, p058_1 20/15, p058_2 8/2, p059_0 24/16, p059_1 7/2, p060_0 33/19, p060_2 7/2, p061_1 7/2, p067_3 11/2, p069_0 12/2, p069_1 10/2, p072_1 12/2, p072_2 10/2, p073_0 36/22, p077_0 30/21, p080_2 12/2, p080_3 10/2 …
text only: p008_0, p010_2, p013_0, p015_0, p015_1, p015_2, p015_3, p015_4, p015_5, p015_6, p016_0, p016_1, p016_2, p016_3, p016_4, p017_0, p019_0, p020_0, p021_0, p021_1, p021_2, p022_0, p022_1, p023_0, p023_1, p023_2, p024_4, p025_1, p025_2, p026_0, p026_1, p026_2, p026_3, p029_0, p029_1, p029_2, p029_3, p030_0, p031_0, p032_0 …

--- p041_0 verbatim ---
(no table found)
```
