  INF MdeModulePkg/Core/Dxe/DxeMain.inf
  INF MdeModulePkg/Universal/PCD/Dxe/Pcd.inf

  INF Binaries/haydn/QcomPkg/Drivers/EnvDxe/EnvDxe.inf

  INF MdeModulePkg/Universal/ReportStatusCodeRouter/RuntimeDxe/ReportStatusCodeRouterRuntimeDxe.inf
  INF MdeModulePkg/Universal/StatusCodeHandler/RuntimeDxe/StatusCodeHandlerRuntimeDxe.inf
  INF ArmPkg/Drivers/CpuDxe/CpuDxe.inf
  INF MdeModulePkg/Core/RuntimeDxe/RuntimeDxe.inf
  INF MdeModulePkg/Universal/SecurityStubDxe/SecurityStubDxe.inf

  INF Binaries/haydn/QcomPkg/Drivers/ShmBridgeDxe/ShmBridgeDxeLA.inf
  INF Binaries/haydn/QcomPkg/Drivers/TzDxe/ScmDxeLA.inf
  INF Binaries/haydn/QcomPkg/Drivers/TzDxe/TzDxeLA.inf

  INF MdeModulePkg/Universal/WatchdogTimerDxe/WatchdogTimer.inf
  INF MdeModulePkg/Universal/CapsuleRuntimeDxe/CapsuleRuntimeDxe.inf
  INF MdeModulePkg/Universal/Variable/RuntimeDxe/VariableRuntimeDxe.inf
  INF EmbeddedPkg/EmbeddedMonotonicCounter/EmbeddedMonotonicCounter.inf
  INF MdeModulePkg/Universal/ResetSystemRuntimeDxe/ResetSystemRuntimeDxe.inf
  INF EmbeddedPkg/RealTimeClockRuntimeDxe/RealTimeClockRuntimeDxe.inf
  INF EmbeddedPkg/MetronomeDxe/MetronomeDxe.inf
  INF MdeModulePkg/Universal/HiiDatabaseDxe/HiiDatabaseDxe.inf
  INF ArmPkg/Drivers/ArmGicDxe/ArmGicDxe.inf
  INF ArmPkg/Drivers/TimerDxe/TimerDxe.inf

  INF Binaries/haydn/QcomPkg/Drivers/ChipInfoDxe/ChipInfoDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/PlatformInfoDxe/PlatformInfoDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/ProjectInfoDxe/ProjectInfoDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/DALSYSDxe/DALSYSDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/HALIOMMUDxe/HALIOMMUDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/HWIODxe/HWIODxe.inf

  INF MdeModulePkg/Universal/DevicePathDxe/DevicePathDxe.inf
  INF MdeModulePkg/Universal/Disk/DiskIoDxe/DiskIoDxe.inf
  INF MdeModulePkg/Universal/Disk/PartitionDxe/PartitionDxe.inf
  INF FatPkg/EnhancedFatDxe/Fat.inf
  INF MdeModulePkg/Universal/Disk/UnicodeCollation/EnglishDxe/EnglishDxe.inf

  INF Binaries/haydn/QcomPkg/Drivers/UFSDxe/UFSDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/CmdDbDxe/CmdDbDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/PwrUtilsDxe/PwrUtilsDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/RpmhDxe/RpmhDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/NpaDxe/NpaDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/ULogDxe/ULogDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/VcsDxe/VcsDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/ClockDxe/ClockDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/ICBDxe/ICBDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/SmemDxe/SmemDxe.inf
  INF MdeModulePkg/Universal/BdsDxe/BdsDxe.inf
  INF EmbeddedPkg/SimpleTextInOutSerial/SimpleTextInOutSerial.inf
  INF MdeModulePkg/Universal/PrintDxe/PrintDxe.inf
  INF MdeModulePkg/Universal/Console/ConPlatformDxe/ConPlatformDxe.inf
  INF MdeModulePkg/Universal/Console/ConSplitterDxe/ConSplitterDxe.inf
  INF MdeModulePkg/Universal/Console/GraphicsConsoleDxe/GraphicsConsoleDxe.inf

!if $(USE_CUSTOM_DISPLAY_DRIVER) == 1
  INF Binaries/haydn/QcomPkg/Drivers/CPRDxe/CPRDxe.inf
!endif
  INF Binaries/haydn/QcomPkg/Drivers/GpiDxe/GpiDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/I2CDxe/I2CDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/SPIDxe/SPIDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/SPMIDxe/SPMIDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/PmicDxe/PmicDxeLa.inf
  INF Binaries/haydn/QcomPkg/Drivers/SdccDxe/SdccDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/TLMMDxe/TLMMDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/FeatureEnablerDxe/FeatureEnablerDxe.inf

!if $(USE_CUSTOM_DISPLAY_DRIVER) == 1
  INF Binaries/haydn/QcomPkg/Drivers/DisplayDxe/DisplayDxe.inf
!else
  INF SiliciumPkg/Drivers/SimpleFbDxe/SimpleFbDxe.inf
!endif

  INF Binaries/haydn/QcomPkg/Drivers/ButtonsDxe/ButtonsDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/ChargerExDxe/ChargerExDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/IPCCDxe/IPCCDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/GLinkDxe/GLinkDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/PmicGlinkDxe/PmicGlinkDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/QcomChargerDxe/QcomChargerDxeLA.inf
  INF Binaries/haydn/QcomPkg/Drivers/UsbPwrCtrlDxe/UsbPwrCtrlDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/TsensDxe/TsensDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/DDRInfoDxe/DDRInfoDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/UsbfnDwc3Dxe/UsbfnDwc3Dxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/XhciPciEmulationDxe/XhciPciEmulationDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/XhciDxe/XhciDxe.inf

  INF MdeModulePkg/Bus/Usb/UsbBusDxe/UsbBusDxe.inf
  INF MdeModulePkg/Bus/Usb/UsbKbDxe/UsbKbDxe.inf
  INF MdeModulePkg/Bus/Usb/UsbMassStorageDxe/UsbMassStorageDxe.inf

  INF Binaries/haydn/QcomPkg/Drivers/UsbMsdDxe/UsbMsdDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/UsbDeviceDxe/UsbDeviceDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/UsbConfigDxe/UsbConfigDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/UsbInitDxe/UsbInitDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/UCDxe/UCDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/RNGDxe/RngDxe.inf
  #INF Binaries/haydn/QcomPkg/Drivers/PILDxe/PILDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/PILProxyDxe/PILProxyDxe.inf
  INF Binaries/haydn/QcomPkg/Drivers/SPSSDxe/SPSSDxe.inf

