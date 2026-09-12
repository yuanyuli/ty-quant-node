# Qlib ComfyUI 节点组

本目录是独立维护的 Qlib ComfyUI 自定义节点仓库。源码、文档、测试和调研材料均不依赖同级节点仓库。

## 目录

- `docs/specs/`：设计规格
- `docs/plans/`：实施计划
- `research/`：Qlib 与 ty-quant 调研源码及下载归档，不作为运行时依赖

开发时通过 junction 接入 ComfyUI：

```powershell
cmd /c mklink /J "E:\ComfyUI_windows_portable-G314\ComfyUI\custom_nodes\qlib-comfyui" "D:\work_station\ty-comfyui-node\qlib-comfyui"
```
