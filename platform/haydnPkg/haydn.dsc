#
# The DSC for haydn (Redmi K40 Pro, SM8350).
#
# Structured after Platforms/Xiaomi/viliPkg/vili.dsc in
# Project-Silicium/Mu-Silicium -- the same SoC and the same 8 GB of DDR -- with
# every board fact replaced by this phone's. What is NOT replaced is the UEFI
# implementation: Mu-Silicium and the Silicium SM8350 support are shared, and
# that is the point of building this rather than extracting; see
# docs/binaries.md for what does come from the handset.
#
# Every address below is from the phone and traceable to docs/hardware.md or
# docs/binaries.md. None is copied from venus or vili.
#
[Defines]
  PLATFORM_NAME                  = haydn
  PLATFORM_GUID                  = 6f2a1c94-3b7e-4d58-9a0c-1e5b8f7d2a63
  PLATFORM_VERSION               = 0.1
  DSC_SPECIFICATION              = 0x00010005
  OUTPUT_DIRECTORY               = Build/haydnPkg
  SUPPORTED_ARCHITECTURES        = AARCH64
  BUILD_TARGETS                  = DEBUG|RELEASE
  SKUID_IDENTIFIER               = DEFAULT
  FLASH_DEFINITION               = haydnPkg/haydn.fdf
  USE_CUSTOM_DISPLAY_DRIVER      = 0

  #
  # 0 = SM8350
  # 1 = SM8350-AB
  # 2 = SM8350-AC
  #
  # This handset is plain SM8350: the GPU reports chipid 0x06060001 and the
  # board is M2012K11C, not the -AB or -AC variant.
  #
  SOC_TYPE                       = 0

!include LahainaPkg/LahainaPkg.dsc.inc

  #
  # The firmware descriptor's load address. venusPkg and viliPkg both use
  # 0x9fd00000, and so does this, because the number is not theirs: it is where
  # SM8350's abl leaves room. abl's own ELF header says it occupies
  # [0x9fa00000, 0x9fa30000) and its entry is 0x9fa00000, so everything from
  # 0x9fa30000 upward is free; 0x9fd00000 is 3 MB past abl's start.
  #
  # Checked against this phone's DRAM and its reserved regions: DRAM begins at
  # 0x80000000, and [0x9fd00000, 0xa3d00000) overlaps none of hyp_region
  # (0x80000000+0x600000), xbl_aop_region (0x80600000+0x260000),
  # res_xbl_uefi_log (0x80880000+0x14000), modem_region (0x8f000000+0x10000000),
  # removed_region (0xd8800000+0x5400000) or splash_region (0xdfc00000+0x2300000).
  #
  FD_BASE                        = 0x9FD00000
  FD_SIZE                        = 0x00200000

[PcdsFixedAtBuild]
  #
  # DDR Memory
  #
  gArmTokenSpaceGuid.PcdSystemMemoryBase|0x80000000

  #
  # UEFI Stack. Inside the FD region's shadow, above the firmware, below the
  # 0xA0000000 boundary where free DDR starts.
  #
  gArmPlatformTokenSpaceGuid.PcdCPUCoresStackBase|0x9FF90000
  gArmPlatformTokenSpaceGuid.PcdCPUCorePrimaryStackSize|0x40000

  #
  # The phone's own identity. Not venus's (Mi 11 / M2011K2G) and not
  # haydnpro's (K40 Pro+ / 12 GB): this is the 8 GB Redmi K40 Pro, which the
  # firmware reports as hardware.sku=haydn and hwversion=4.9.0.
  #
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemManufacturer|"Xiaomi"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemModel|"Redmi K40 Pro"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemRetailModel|"haydn"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemRetailSku|"M2012K11C"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemBoardModel|"haydn"

  #
  # The frame buffer. 1080x2400 from the panel the bootloader names
  # (qcom,mdss_dsi_k11_38_08_0a_dsc_cmd), 32bpp as the vendor's own config.
  #
  gSiliciumPkgTokenSpaceGuid.PcdFrameBufferWidth|1080
  gSiliciumPkgTokenSpaceGuid.PcdFrameBufferHeight|2400
  gSiliciumPkgTokenSpaceGuid.PcdFrameBufferColorDepth|32

  #
  # Platform PEI
  #
  gQcomPkgTokenSpaceGuid.PcdPlatformType|"LA"

!include MdePkg/MdeLibs.dsc.inc

[LibraryClasses]
  #
  # Memory Libraries
  #
  MemoryMapLib|haydnPkg/Library/MemoryMapLib/MemoryMapLib.inf

  #
  # QCOM Libraries
  #
  ConfigurationMapLib|haydnPkg/Library/ConfigurationMapLib/ConfigurationMapLib.inf

  BaseLib|MdePkg/Library/BaseLib/BaseLib.inf
  BaseMemoryLib|MdePkg/Library/BaseMemoryLib/BaseMemoryLib.inf
  DevicePathLib|MdePkg/Library/UefiDevicePathLib/UefiDevicePathLib.inf
  FdtLib|MdePkg/Library/BaseFdtLib/BaseFdtLib.inf
  MemoryAllocationLib|MdePkg/Library/UefiMemoryAllocationLib/UefiMemoryAllocationLib.inf
  PcdLib|MdePkg/Library/BasePcdLibNull/BasePcdLibNull.inf
  PrintLib|MdePkg/Library/BasePrintLib/BasePrintLib.inf
  UefiApplicationEntryPoint|MdePkg/Library/UefiApplicationEntryPoint/UefiApplicationEntryPoint.inf
  UefiBootServicesTableLib|MdePkg/Library/UefiBootServicesTableLib/UefiBootServicesTableLib.inf
  UefiDriverEntryPoint|MdePkg/Library/UefiDriverEntryPoint/UefiDriverEntryPoint.inf
  UefiLib|MdePkg/Library/UefiLib/UefiLib.inf
  UefiRuntimeServicesTableLib|MdePkg/Library/UefiRuntimeServicesTableLib/UefiRuntimeServicesTableLib.inf
  DebugPrintErrorLevelLib|MdePkg/Library/BaseDebugPrintErrorLevelLib/BaseDebugPrintErrorLevelLib.inf
  DebugLib|MdePkg/Library/UefiDebugLibStdErr/UefiDebugLibStdErr.inf

[PcdsFixedAtBuild]
  gEfiMdePkgTokenSpaceGuid.PcdDebugPrintErrorLevel|0x80000000
  gEfiMdePkgTokenSpaceGuid.PcdDebugPropertyMask|0x07
  gArmTokenSpaceGuid.PcdArmPrimaryCore|0
  gArmTokenSpaceGuid.PcdArmPrimaryCoreMask|0xFF

[Components]
  #
  # UniXNU's own components are not in the Mu-Silicium tree. A first build has
  # to succeed without them; haydn.fdf names them where they go once they exist.
  #
  # UniXNUPkg/Application/UniXNU/UniXNU.inf
  # DarwinBootPkg/Driver/DarwinBoot.inf
