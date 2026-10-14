<div align="center">

[English](README.md) · [Deutsch](README.de.md) · [Русский](README.ru.md) · [Français](README.fr.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Português (Brasil)](README.pt-BR.md) · [Polski](README.pl.md) · [Українська](README.uk.md) · [日本語](README.ja.md) · [简体中文](README.zh-CN.md)

</div>

# PicardWulf v1.0

**为 MusicBrainz Picard 3.0 提供跨平台发行版本检索、自动元数据选择和安全标签写入。**

> **状态：**候选版本。已通过本地测试，但尚未在 BMAX-B6 上完成插件运行、真实 API 请求和音频文件写入的端到端验证。

## 功能

- 聚合 MusicBrainz、Deezer 和 Apple/iTunes；配置合法 API 凭据后可查询 Spotify、SoundCloud 与 Last.fm。
- 通过 **添加文件夹** 载入音乐后，根据曲名、艺术家、专辑、时长、ISRC 和真实标识符比较候选发行版本。
- **得分最高且可信的来源获胜**，不会默认优先 MusicBrainz。Deezer、Spotify 等来源也可成为最终元数据来源。
- 如果发行版本不同、标识符冲突或分数接近，则不会自动修改，需人工审阅。
- Picard 原生专辑面板只接收经过验证的 MusicBrainz Release/Recording MBID。其他服务的专辑 ID 不会被伪装成 MBID。
- 自动选择默认只更新 Picard 内的元数据。**自动写入音频文件默认关闭**；明确启用后，每次写入前都会对完整音频文件进行备份并验证 SHA-256。
- 保留 NEOWULF 文件命名功能，防止将个人精选专辑错误归入 Various Artists。*Curtain Call 2* 应归属于 Eminem。

## Windows 安装

关闭 Picard **3.0**，解压安装包，并以桌面用户（BMAX-B6 上为 `megal`）运行 **`Install-NEOWULF.cmd`**。安装目录为 `%APPDATA%\MusicBrainz\Picard\plugins3\neowulf_picard_repair`，不会调用有缺陷的 `picard-cli.exe`。启动 Picard 后在 **Options → Plugins** 中启用插件。

## 使用与安全

**File → Add Folder** 启动后台搜索。**Tools → PicardWulf** 提供来源选择和可选的备份写入；**Tools → NEOWULF** 提供来源状态及命名修复。自动应用通常要求至少 **93.5%** 的明确匹配。查询字段会发送给已启用的服务，并遵守各 API 的授权和速率限制。BMAX-B6 实机验证仍待完成。

## 开发

```bash
python -m unittest discover -s tests -v
```

[详细英文文档](README.md) · [更新日志](CHANGELOG.md) · [待办状态](LAST_TASKS.md) · [许可证](LICENSE)
