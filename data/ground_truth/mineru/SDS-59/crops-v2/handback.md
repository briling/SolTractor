# SDS-59: node hand-back (second crop pass)

- mineru: `{"mineru_version":"4.0.12","python_version":"3.12.3"}`
- GPU / driver: NVIDIA A100-SXM4-80GB, 580.178.04
- CUDA (driver): CUDA Version: 13.0; PyTorch build cu130, vLLM 0.28.0
- OS: Ubuntu 24.04.5 LTS
- engine: vllm-async-engine (both passes), tier standard; page pass with --ocr-mode ocr

## Crop pass
- 11:03 SDS-59-crops ok 373s (one `mineru-kit parse <dir>` process, one engine; crops are parsed one image at a time, so no batching across crops)

```
crops in manifest: 336  |  with <table>: 214  |  text only: 122  |  no output found: 0
data rows - n_num_lines: <-3:13 -3:17 -2:11 -1:84 0:87 +1:2 >+1:0
within tolerance (-1..+1): 173 of 214 tables (81 %)
five worst (crop, n_num_lines, data rows): p259_0 29/20, p318_0 17/11, p214_0 28/23, p054_0 20/16, p225_0 28/24
outside tolerance (crop, n_num_lines, data rows): p051_0 20/17, p053_0 16/13, p054_0 20/16, p056_0 18/15, p057_0 15/12, p058_0 17/14, p060_0 14/11, p074_0 15/13, p088_0 22/20, p091_0 23/20, p093_0 20/17, p102_0 16/14, p150_0 15/13, p169_1 5/3, p194_0 19/17, p207_0 20/18, p208_0 18/15, p214_0 28/23, p217_0 15/12, p218_0 20/17, p220_0 15/12, p225_0 28/24, p231_0 17/14, p258_0 21/17, p259_0 29/20, p274_0 13/9, p276_0 14/11, p277_0 13/11, p287_0 14/12, p318_0 17/11, p320_0 16/13, p322_0 19/15, p324_0 19/15, p325_0 17/13, p326_0 17/14, p334_0 12/9, p336_0 13/9, p339_0 13/9, p341_0 13/9, p348_0 13/11 …
text only: p035_0, p046_0, p046_1, p047_0, p047_1, p048_0, p048_1, p049_0, p049_1, p050_0, p050_1, p082_0, p094_0, p104_1, p108_0, p109_0, p114_0, p114_1, p117_0, p117_1, p118_0, p118_1, p121_0, p123_0, p124_0, p124_1, p125_0, p125_1, p126_0, p126_1, p131_0, p135_0, p135_1, p138_1, p140_0, p147_1, p159_1, p160_0, p160_1, p161_0 …

--- p041_0 verbatim ---
(no table found)
```
