OBS PTZ — Windows x64 安装说明

1. 将整个 ZIP 解压到一个文件夹，保留 obs-ptz 目录结构。
2. 完全退出 OBS，包括托盘中的 OBS。
3. 双击 install.bat，在 Windows 提示时允许管理员权限。
4. 安装成功后重新启动 OBS。支持 OBS Studio 32.0.4 或更高版本的 x64；本次实测为 32.0.4。

默认安装目录：C:\ProgramData\obs-studio\plugins\obs-ptz
升级备份目录：C:\ProgramData\obs-studio\plugin-backups
脚本只替换插件文件，OBS 配置和场景数据保存在其它目录。

Soft PTZ 在切换场景时默认自动解锁，仍可临时手动锁定；实体 PTZ 摄像机保留播出保护。
PTZ 设置中右侧区域用于显示当前源的实时预览，包括文字源。

手工安装：将 ZIP 内 obs-ptz 文件夹复制到 C:\ProgramData\obs-studio\plugins。
如果旧版本曾安装在 OBS 程序目录等其它位置，请避免重复加载旧的 obs-ptz.dll。

这是未签名的 fork 测试构建。版本和源码提交见 BUILD-INFO.txt；文件哈希见 SHA256SUMS.txt。
源码和许可证：https://github.com/iesv/obs-ptz/tree/fix/soft-ptz-windows
本包附有 GPL 许可证，详见 LICENSE。
