# SDS-62: node hand-back

- mineru: `{"mineru_version":"4.0.12","python_version":"3.12.3"}`
- GPU / driver: NVIDIA A100-SXM4-80GB, 580.178.04
- CUDA (driver): CUDA Version: 13.0; PyTorch build cu130, vLLM 0.28.0
- OS: Ubuntu 24.04.5 LTS
- engine: vllm-async-engine (both passes), tier standard; page pass with --ocr-mode ocr

## Page pass
- 13:52 SDS-62 ok 292s; last inference window pages=401 speed=1.858 page/s

## Crop pass
- 16:41 SDS-62-crops ok 889s (one `mineru-kit parse <dir>` process, one engine; crops are parsed one image at a time, so no batching across crops)

```
crops in manifest: 474  |  with <table>: 364  |  text only: 110  |  no output found: 0
n_lines - <tr> distribution: 0:4 1:11 2:31 3:52 4:41 5:28 6:25 7:15 8:21 9:13 10:15 11:16 12:2 13:3 14:2 15:1 16:3 17:5 18:10 19:2 20:2 21:4 22:2 23:2 24:1 25:3 27:1 28:1 29:1 31:4 32:1 33:2 34:2 35:1 36:5 37:3 38:4 39:3 40:2 41:1 42:3 43:3 44:2 45:3 46:2 47:2 49:2 50:1 55:1
within tolerance (-3..+4): 139 of 364 tables (38 %)
outside tolerance (crop, n_lines, <tr>): p006_1 18/1, p007_0 57/2, p007_1 26/2, p007_2 11/3, p008_0 43/3, p015_0 18/5, p017_0 41/3, p024_1 29/8, p024_2 28/1, p024_3 21/6, p025_2 14/6, p025_3 12/6, p026_0 51/35, p026_1 18/8, p027_0 50/25, p028_0 51/15, p029_0 40/32, p033_0 21/12, p035_0 14/3, p039_0 21/16, p040_0 16/9, p049_1 11/2, p049_2 7/2, p051_0 14/6, p052_0 37/30, p053_0 12/7, p054_0 33/23, p055_0 9/4, p056_0 27/20, p057_1 13/3, p058_1 14/7, p061_1 44/30, p063_1 45/32, p064_1 46/41, p068_1 23/13, p069_1 21/16, p070_0 17/8, p071_0 11/5, p072_1 14/3, p072_2 12/3 …
text only: p005_0, p005_1, p005_2, p005_3, p006_0, p008_1, p008_2, p008_3, p011_0, p012_0, p013_0, p014_0, p014_1, p016_0, p017_1, p018_0, p023_0, p023_1, p024_0, p025_0, p025_1, p025_4, p028_1, p028_2, p030_0, p046_0, p055_1, p065_1, p074_1, p077_1, p077_2, p088_0, p090_0, p108_0, p108_1, p110_2, p118_2, p122_1, p127_0, p127_1 …

--- p041_0 verbatim ---
<table><tr><td>T/K</td><td><eq>p_1/kPa^a</eq></td><td><eq>L^b</eq></td><td><eq>10^3x_1^a</eq></td><td>T/K</td><td><eq>p_1/kPa^a</eq></td><td><eq>L^b</eq></td><td><eq>10^3x_1^a</eq></td></tr><tr><td rowspan="5">298.15</td><td>99.1</td><td>0.816</td><td>0.589</td><td rowspan="5">298.15</td><td>139.3</td><td>0.817</td><td>0.829</td></tr><tr><td>100.3</td><td>0.817</td><td>0.597</td><td>141.8</td><td>0.819</td><td>0.854</td></tr><tr><td>106.7</td><td>0.815</td><td>0.633</td><td>153.7</td><td>0.818</td><td>0.916</td></tr><tr><td>112.1</td><td>0.817</td><td>0.667</td><td>165.7</td><td>0.819</td><td>0.988</td></tr><tr><td>127.3</td><td>0.8165</td><td>0.757</td><td>180.1</td><td>0.820</td><td>1.075</td></tr></table>
```
