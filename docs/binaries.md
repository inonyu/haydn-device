# haydn 的 Binaries 清单

从 `haydn`（Redmi K40 Pro / SM8350）的分区直接读出，2026-11-12。

---

## 一、结论先行

**UEFI 本身不是从手机提取的，是从源码编译的。**

我之前在 `docs/uefi.md` 里写过「从 xbl_a/xbl_b 和 abl 提取固件卷」——
**这句话是错的**，这一轮把它证伪了。

`abl_a` 是 ELF32 ARM 的 LK（Little Kernel），`xbl_a` 是 ELF64 AArch64 的先加载阶段。
两个都不是 UEFI 固件卷。这台机器上连 `uefi` 分区都不存在。

需要从手机提取的是 `Binaries/` 里的**固件件**——见下表。

---

## 二、提取到的六个件

| 分区 | 分区大小 | 真实内容 | 类型 | 机器 | 入口 |
|---|---|---|---|---|---|
| `devcfg_a` | 262,144 | 52,460 | ELF64 | AArch64 | `0x1c003000` |
| `tz_a` | 4,194,304 | 3,765,662 | ELF64 | AArch64 | `0x14680000` |
| `aop_a` | 524,288 | 244,056 | ELF32 | ARM | `0xb000009` |
| `qupfw_a` | 131,072 | 57,249 | ELF32 | 0xa4 | `0x0` |
| `uefisecapp_a` | 2,097,152 | 124,825 | ELF32 | ARM | `0x0` |
| `imagefv_a` | 2,097,152 | 2,097,152 | ELF32 | ARM | `0x0` |

### SHA-256

```
devcfg_a      6a0b1f33add9c072d70b9b5a103d6718705d848b3034a3ff86aa461686709943
tz_a          1e940efd1d9a6c832a7da9687a4918d72f8eb48ccd7ed5b469f5b2c70866b158
aop_a         420c0c56346f2c6a46b4e765aa834d30501668ce869b9584516a597de9e52cec
qupfw_a       101c8c40393bbfdeeb4d70328bae41f63192450aabbea4bb60c00cd062866edb
uefisecapp_a  f3ccc5a7f40a00575cc7d5ec0c7397753c8a8c5a02f9eb517580e1f3706c5b55
imagefv_a     183a3a5fd94451977624c3093457ba3a7c0980e9b33cb4f3170300effe8ec43d
```

---

## 三、每一个是什么

### `devcfg_a` — 设备配置

262,144 字节分区，52,460 字节真实内容。
ELF64 AArch64，入口 `0x1c003000`。

这是 DDR 训练参数和早期外设初始化。**必须替换成 haydn 自己的**——
DDR 时序和这块板子的走线有关，用兄弟板的会跑在不该跑的时刻上。

### `tz_a` — TrustZone

4,194,304 字节分区，**3,765,662 字节真实内容**（最大的一块）。
ELF64 AArch64，入口 `0x14680000`。

安全世界。GPU 的 zap shader、UFS 的 ICE、HDCP 都过它。
**不可替换**，只能用这块板子自己的。

### `aop_a` — Always-On Processor

524,288 字节分区，244,056 字节真实内容。
ELF32 **ARM**（不是 AArch64），入口 `0xb000009`。

低功耗岛的处理器。RSCC（第 7 步）就是和它打交道。

### `qupfw_a` — QUP 固件

131,072 字节分区，57,249 字节真实内容。
ELF32，**`e_machine = 164`（0xA4）**——这是个不常见的值。

QUP 是串行引擎（SPI/I2C/UART 的硬件加速器）。触摸屏的 SPI 走的就是它。
`e_machine = 164` 可能是高通私有的协处理器架构。

### `uefisecapp_a` — UEFI 安全应用

2,097,152 字节分区，124,825 字节真实内容。
ELF32 ARM。

UEFI 环境下跑的安全应用（签名校验之类）。

### `imagefv_a` — 开机图片

2,097,152 字节分区，**全部被使用**。

里面有 `_FVH` 签名（`0x3028`），FileSystemGuid 是 `8c8ce578-8a3d-4f1c-9935-896185c32dd3`，
正是 **EFI_FIRMWARE_FILE_SYSTEM2_GUID**。FvLength 声明 2,084,864。

但**内容是压缩的**：

```
  区域              熵       判断
  0x0000-0x3000    3.62     文本/空白（ELF 头）
  0x3000-0x3400    7.68     压缩或加密
  0x3400-0x10000   8.00     压缩
  0x10000-0x200000 0.79     稀疏（457 个非零区块）
```

**这不是可以用的 UEFI 卷。** 它是一个包装了图片数据的壳，
熵 8.00 说明用了 Tiano/LZMA 压缩。解出来大概率是开机 logo。

---

## 四、对比：venus 的 `[firmware]` 段

```
[firmware]
dsc = "Platforms/Xiaomi/venusPkg/venus.dsc"
fd  = "Build/venusPkg/{target}_CLANGPDB/FV/SILICIUM_UEFI.fd"   ← Build/ 里的编译产物
packages = ["{uefi}", "{uefi}/Platforms/Xiaomi", "{uefi}/Silicon/Qualcomm",
            "{uefi}/Silicon/Silicium", ..., "{tree}/drivers/DarwinBoot"]
```

三个关键点：

1. **`fd` 指向 `Build/`**——是编译出来的，不是提取的
2. **`Silicon/Qualcomm` + `Silicon/Silicium`**——开源的 SoC 支持代码
3. **`{tree}/package` + `{tree}/drivers/DarwinBoot`**——移植自己的代码

---

## 五、haydnPkg 真正需要什么

```
Platforms/Xiaomi/haydnPkg/
├─ haydn.dsc                    ← 从 venus.dsc 改
├─ haydn.fdf                    ← 从 venus.fdf 改
├─ include/
│   └─ Platform.h               ← 内存基址、堆大小、堆栈
├─ Binaries/
│   ├─ devcfg_haydn.elf         ← 本机 devcfg
│   ├─ tz_haydn.mbn             ← 本机 tz
│   ├─ aop_haydn.mbn            ← 本机 aop
│   ├─ qupfw_haydn.elf          ← 本机 qupfw
│   └─ uefisecapp_haydn.elf     ← 本机 uefisecapp
├─ Library/
│   └─ PlatformBootManagerLib/
└─ Drivers/
    └─ ...
```

**关键：`Binaries/` 里只有固件件，没有 UEFI 本体。**

---

## 六、`docs/uefi.md` 要改的地方

原文：

```
2. Extract the firmware volumes from xbl_a/xbl_b and the abl image.
```

改成：

```
2. Extract the firmware *pieces* the UEFI build consumes, not the UEFI
   volume itself. The volume is compiled; what comes from the phone is
   devcfg, tz, aop, qupfw and uefisecapp. abl is LK (ELF32 ARM) and xbl is
   the first loader (ELF64); neither holds a firmware volume.
```

---

## 七、下一步

1. 把六个件放进 `haydnPkg/Binaries/` 的骨架（本仓库只放清单和哈希，不放二进制）
2. 从 `venusPkg` 生成 `haydn.dsc` / `haydn.fdf`，改内存基址
3. 确认 FD 基址：venus 记录里的 `0x9fd00000` 是它自己的布局
