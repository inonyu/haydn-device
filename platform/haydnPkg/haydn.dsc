##
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
# docs/binaries.md.
#
# The shape is vili.dsc's on purpose, down to the two sections and nothing
# else. An earlier draft added a full [LibraryClasses] block and it failed:
#
#     haydn.dsc(...): error 1001: Module type [SEC] is not supported by
#     library instance [.../UefiDebugLibStdErr/UefiDebugLibStdErr.inf]
#
# A bare [LibraryClasses] section in the DSC applies to every module type in the
# build, SEC included, and UefiDebugLibStdErr does not support SEC. LahainaPkg's
# include chain already supplies the right library for each module type, so the
# only entries that belong here are the two this package owns.
##
[Defines]
  PLATFORM_NAME                  = haydn
  PLATFORM_GUID                  = 6f2a1c94-3b7e-4d58-9a0c-1e5b8f7d2a63
  PLATFORM_VERSION               = 0.1
  DSC_SPECIFICATION              = 0x00010005
  OUTPUT_DIRECTORY               = Build/haydnPkg
  SUPPORTED_ARCHITECTURES        = AARCH64
  BUILD_TARGETS                  = RELEASE|DEBUG
  SKUID_IDENTIFIER               = DEFAULT
  FLASH_DEFINITION               = haydnPkg/haydn.fdf

  #
  # This board's panel tables are not in the venus set the binaries were seeded
  # from, so the custom display driver stays off for the first build.
  #
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

[LibraryClasses]
  #
  # Memory Libraries
  #
  MemoryMapLib|haydnPkg/Library/MemoryMapLib/MemoryMapLib.inf

  #
  # QCOM Libraries
  #
  ConfigurationMapLib|haydnPkg/Library/ConfigurationMapLib/ConfigurationMapLib.inf

[Components]
  #
  # UniXNU's own components are not in the Mu-Silicium tree. A first build has
  # to succeed without them; haydn.fdf names them where they go once they exist.
  #
  # UniXNUPkg/Application/UniXNU/UniXNU.inf
  # DarwinBootPkg/Driver/DarwinBoot.inf
  #
  # No AcpiTables.inf: no haydn tables exist, and copying venus's or vili's
  # would put another board's panel and PMIC description in this volume. That is
  # the mistake docs/hardware.md exists to prevent.
