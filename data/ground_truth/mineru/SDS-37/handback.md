# SDS-37: node hand-back

- mineru: `{"mineru_version":"4.0.12","python_version":"3.12.3"}`
- GPU / driver: NVIDIA A100-SXM4-80GB, 580.178.04
- CUDA (driver): CUDA Version: 13.0; PyTorch build cu130, vLLM 0.28.0
- OS: Ubuntu 24.04.5 LTS
- engine: vllm-async-engine (both passes), tier standard; page pass with --ocr-mode ocr

## Page pass
- 14:01 SDS-37 ok 330s; last inference window pages=547 speed=2.156 page/s

## Crop pass
- 17:10 SDS-37-crops ok 638s (one `mineru-kit parse <dir>` process, one engine; crops are parsed one image at a time, so no batching across crops)

```
crops in manifest: 515  |  with <table>: 298  |  text only: 217  |  no output found: 0
n_lines - <tr> distribution: 0:6 1:13 2:81 3:31 4:19 5:18 6:14 7:10 8:3 9:4 10:1 11:7 12:3 13:1 14:4 15:3 16:4 17:2 18:4 19:2 20:7 21:4 22:4 23:7 24:6 25:4 26:2 27:3 28:3 29:3 30:1 31:1 32:3 33:2 35:3 36:1 37:2 39:4 42:2 43:2 45:1 46:1 47:1 54:1
within tolerance (-3..+4): 150 of 298 tables (50 %)
outside tolerance (crop, n_lines, <tr>): p007_0 21/2, p009_0 41/4, p009_1 6/1, p010_0 30/6, p013_0 30/1, p014_0 48/12, p014_1 21/6, p016_0 33/4, p021_0 9/3, p025_0 29/6, p027_0 20/9, p028_0 34/1, p030_0 28/18, p037_0 22/8, p039_0 30/13, p041_0 29/6, p042_0 35/12, p042_1 18/7, p046_0 14/6, p049_0 25/5, p058_0 15/10, p061_0 28/5, p062_0 44/19, p063_0 48/3, p064_0 57/3, p065_0 36/8, p066_0 34/2, p070_0 29/5, p070_1 27/5, p079_0 8/3, p081_0 14/7, p082_0 27/16, p083_0 48/36, p084_0 55/40, p085_0 45/27, p086_0 45/2, p087_0 44/7, p088_0 55/16, p090_0 44/2, p090_1 15/4 …
text only: p007_1, p007_2, p007_3, p007_4, p008_0, p008_1, p008_4, p008_5, p008_6, p011_0, p014_2, p015_0, p021_1, p021_2, p024_0, p026_0, p029_0, p029_1, p031_0, p031_1, p032_0, p038_0, p038_1, p040_0, p043_0, p044_0, p044_1, p047_0, p048_0, p050_0, p050_1, p060_0, p067_0, p067_1, p068_0, p071_0, p073_0, p078_0, p080_0, p085_1 …

--- p041_0 verbatim ---
<table><tr><td colspan="2">EXPERIMENTAL VALUES:The solubility of cyclopentane in water at 25°C was reported to be 160.0 mg(1)/kg(2).The corresponding mass percent and mole fraction, <eq>x_{1}</eq>, calculated by compiler are 0.0160 g (1)/100 g sln and 4.11 x <eq>10^{-5}</eq>.</td></tr><tr><td colspan="2">Editor&#x27;s Note: Based on the results for this and other hydrocarbon-water systems, uncertainty exists about whether the datum compiled here is independent of that of Price for the same system (see previous page).</td></tr><tr><td colspan="2">AUXILIARY INFORMATION</td></tr><tr><td rowspan="3">METHOD/APPARATUS/PROCEDURE:Saturated solutions of (1) in (2) were prepared in two ways. First, 200 μL of (1) was injected into 20 mL of (2) and thermostatted at 25°C. Second, the mixture of (1) and (2) as above was thermostatted at 70°C and then cooled to 25°C.The time required to obtain equilibrium was three weeks. The solubility of (1) in (2) was measured by glc. A Perkin-Elmer model F-11 gas chromatograph equipped with a 100-150-mesh Porasil column (70°C) and a flame ionization detector was used. Saturated solutions of heptane in (2) were used as standard solutions.</td><td>SOURCE AND PURITY OF MATERIALS:(1) not specified.(2) not specified.</td></tr><tr><td>ESTIMATED ERROR:soly. 4.0 mg(1)/kg(2) (standard deviation from 7-9 determinations)</td></tr><tr><td>REFERENCES:</td></tr></table>
```
