# SDS-38: node hand-back

- mineru: `{"mineru_version":"4.0.12","python_version":"3.12.3"}`
- GPU / driver: NVIDIA A100-SXM4-80GB, 580.178.04
- CUDA (driver): CUDA Version: 13.0; PyTorch build cu130, vLLM 0.28.0
- OS: Ubuntu 24.04.5 LTS
- engine: vllm-async-engine (both passes), tier standard; page pass with --ocr-mode ocr

## Page pass
- 14:06 SDS-38 ok 332s; last inference window pages=581 speed=2.277 page/s

## Crop pass
- 17:23 SDS-38-crops ok 580s (one `mineru-kit parse <dir>` process, one engine; crops are parsed one image at a time, so no batching across crops)

```
crops in manifest: 575  |  with <table>: 242  |  text only: 333  |  no output found: 0
n_lines - <tr> distribution: 0:3 1:20 2:45 3:39 4:32 5:17 6:7 7:7 8:5 9:3 10:2 11:2 12:1 13:2 14:1 15:3 16:1 18:2 19:4 20:4 21:2 22:3 23:2 24:5 25:7 26:3 27:1 28:1 29:4 30:1 31:1 33:1 34:1 36:2 37:4 39:2 44:1 45:1
within tolerance (-3..+4): 139 of 242 tables (57 %)
outside tolerance (crop, n_lines, <tr>): p008_0 21/2, p010_0 41/4, p011_0 30/4, p012_0 15/3, p015_0 48/12, p015_1 21/6, p015_3 16/5, p017_0 33/4, p031_0 38/5, p032_0 30/10, p033_0 24/1, p048_0 48/14, p049_0 33/2, p051_0 41/17, p056_0 14/8, p058_0 13/8, p066_0 49/4, p069_0 44/15, p073_0 12/7, p078_0 37/11, p081_0 34/12, p082_0 42/3, p083_0 45/25, p084_0 44/7, p085_0 38/2, p086_0 47/8, p087_0 46/2, p091_0 40/17, p093_0 25/5, p106_1 10/2, p109_0 35/13, p109_1 18/3, p117_0 11/4, p124_0 10/4, p128_0 32/7, p129_0 33/13, p129_1 16/3, p130_0 29/11, p133_0 27/6, p142_0 30/5 …
text only: p008_1, p008_2, p008_3, p008_4, p009_0, p009_1, p009_4, p009_5, p009_6, p014_0, p015_2, p015_4, p016_0, p023_0, p024_0, p027_0, p029_0, p034_0, p034_1, p036_0, p039_0, p040_0, p043_0, p046_0, p047_0, p050_0, p050_1, p052_0, p057_0, p059_0, p062_0, p065_0, p067_0, p068_0, p068_1, p070_0, p074_0, p075_0, p076_0, p079_0 …

--- p041_0 verbatim ---
<table><tr><td>EXPERIMENTAL VALUES:</td></tr><tr><td>The solubility of o-xylene in water at 25°C was reported to be 167.0 mg(1)/kg(2).</td></tr><tr><td>The corresponding mass percent and mole fraction, <eq>x_1</eq>, calculated by compiler are 0.0167 g(1)/100 g sln and 2.83 x <eq>10^{-5}</eq>.</td></tr><tr><td>Editor&#x27;s Note: Based on the results for this and other hydrocarbon-water systems, uncertainty exists about whether the datum compiled here is independent of that of Price for the same system (see previous page).</td></tr></table>
```
