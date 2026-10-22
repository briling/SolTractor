# SDS-62: node hand-back (second crop pass)

- mineru: `{"mineru_version":"4.0.12","python_version":"3.12.3"}`
- GPU / driver: NVIDIA A100-SXM4-80GB, 580.178.04
- CUDA (driver): CUDA Version: 13.0; PyTorch build cu130, vLLM 0.28.0
- OS: Ubuntu 24.04.5 LTS
- engine: vllm-async-engine (both passes), tier standard; page pass with --ocr-mode ocr

## Crop pass
- 10:56 SDS-62-crops ok 585s (one `mineru-kit parse <dir>` process, one engine; crops are parsed one image at a time, so no batching across crops)

```
crops in manifest: 307  |  with <table>: 253  |  text only: 54  |  no output found: 0
data rows - n_num_lines: <-3:61 -3:73 -2:66 -1:44 0:9 +1:0 >+1:0
within tolerance (-1..+1): 53 of 253 tables (21 %)
five worst (crop, n_num_lines, data rows): p253_1 40/20, p264_0 23/3, p372_0 19/0, p192_0 24/8, p265_0 17/1
outside tolerance (crop, n_num_lines, data rows): p031_0 23/21, p032_0 8/6, p034_0 10/8, p035_0 8/0, p036_0 29/26, p037_0 4/2, p037_1 16/12, p038_0 4/2, p038_1 5/2, p039_0 17/15, p040_0 10/8, p041_0 7/5, p041_1 8/6, p043_0 7/5, p043_1 11/9, p044_0 10/8, p045_0 18/16, p048_0 3/1, p048_1 11/9, p049_0 4/1, p049_1 4/1, p050_0 32/30, p051_0 9/4, p052_0 31/29, p053_0 9/6, p054_0 24/22, p055_0 6/3, p056_0 19/11, p057_0 21/18, p059_0 21/19, p060_0 23/21, p071_0 6/4, p072_0 35/33, p073_0 24/22, p075_0 8/6, p076_0 7/5, p076_1 10/8, p078_0 16/14, p079_0 23/21, p080_0 9/7 …
text only: p046_0, p065_1, p068_1, p074_1, p090_0, p153_0, p164_0, p166_0, p171_0, p175_1, p179_0, p186_1, p198_0, p200_0, p206_0, p207_0, p210_0, p214_1, p217_0, p226_0, p232_0, p233_0, p234_0, p235_0, p239_0, p242_1, p246_1, p258_1, p263_1, p277_1, p280_0, p289_0, p290_1, p299_1, p305_1, p309_0, p312_1, p319_0, p338_0, p339_0 …

--- p041_0 verbatim ---
<table><tr><td>T/K</td><td><eq>p_1/kPa^a</eq></td><td><eq>L^b</eq></td><td><eq>10^3x_1^a</eq></td><td>T/K</td><td><eq>p_1/kPa^a</eq></td><td><eq>L^b</eq></td><td><eq>10^3x_1^a</eq></td></tr><tr><td rowspan="5">298.15</td><td>99.1</td><td>0.816</td><td>0.589</td><td rowspan="5">298.15</td><td>139.3</td><td>0.817</td><td>0.829</td></tr><tr><td>100.3</td><td>0.817</td><td>0.597</td><td>141.8</td><td>0.819</td><td>0.854</td></tr><tr><td>106.7</td><td>0.815</td><td>0.633</td><td>153.7</td><td>0.818</td><td>0.916</td></tr><tr><td>112.1</td><td>0.817</td><td>0.667</td><td>165.7</td><td>0.819</td><td>0.988</td></tr><tr><td>127.3</td><td>0.8165</td><td>0.757</td><td>180.1</td><td>0.820</td><td>1.075</td></tr></table>
```
