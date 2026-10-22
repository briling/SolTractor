# SDS-38: node hand-back (second crop pass)

- mineru: `{"mineru_version":"4.0.12","python_version":"3.12.3"}`
- GPU / driver: NVIDIA A100-SXM4-80GB, 580.178.04
- CUDA (driver): CUDA Version: 13.0; PyTorch build cu130, vLLM 0.28.0
- OS: Ubuntu 24.04.5 LTS
- engine: vllm-async-engine (both passes), tier standard; page pass with --ocr-mode ocr

## Crop pass
- 10:47 SDS-38-crops ok 528s (one `mineru-kit parse <dir>` process, one engine; crops are parsed one image at a time, so no batching across crops)

```
crops in manifest: 407  |  with <table>: 165  |  text only: 242  |  no output found: 0
data rows - n_num_lines: <-3:20 -3:34 -2:44 -1:61 0:6 +1:0 >+1:0
within tolerance (-1..+1): 67 of 165 tables (41 %)
five worst (crop, n_num_lines, data rows): p069_0 17/12, p392_0 13/8, p427_0 14/9, p432_0 8/3, p532_0 11/6
outside tolerance (crop, n_num_lines, data rows): p026_0 4/0, p028_0 2/0, p037_0 3/0, p038_0 6/4, p041_0 3/0, p051_0 12/9, p054_0 3/0, p056_0 6/4, p058_0 8/6, p060_0 3/0, p069_0 17/12, p072_0 3/0, p073_0 6/2, p077_0 3/0, p091_0 13/9, p099_0 6/4, p105_0 3/0, p111_0 7/5, p117_0 4/0, p119_0 3/0, p122_0 6/4, p124_0 3/0, p129_0 8/6, p133_0 4/0, p139_0 6/4, p141_0 8/6, p143_0 7/4, p149_0 7/4, p153_0 5/3, p180_0 3/0, p188_0 6/4, p193_0 4/0, p196_0 6/4, p200_0 2/0, p205_0 6/4, p206_0 6/4, p215_0 8/6, p229_0 4/0, p234_0 5/3, p236_0 3/0 …
text only: p027_0, p029_0, p034_0, p036_0, p039_0, p040_0, p043_0, p050_0, p057_0, p059_0, p062_0, p068_0, p074_0, p075_0, p076_0, p079_0, p088_0, p089_0, p090_0, p093_0, p095_0, p098_0, p101_0, p102_0, p103_0, p104_0, p112_0, p113_0, p114_0, p115_0, p116_0, p120_0, p121_0, p123_0, p131_0, p132_0, p142_0, p144_0, p145_0, p146_0 …

--- p041_0 verbatim ---
<table><tr><td>EXPERIMENTAL VALUES:</td></tr><tr><td>The solubility of o-xylene in water at 25°C was reported to be 167.0 mg(1)/kg(2).</td></tr><tr><td>The corresponding mass percent and mole fraction, <eq>x_1</eq>, calculated by compiler are 0.0167 g(1)/100 g sln and 2.83 x <eq>10^{-5}</eq>.</td></tr><tr><td>Editor&#x27;s Note: Based on the results for this and other hydrocarbon-water systems, uncertainty exists about whether the datum compiled here is independent of that of Price for the same system (see previous page).</td></tr></table>
```
