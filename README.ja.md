<div align="center">

[English](README.md) · [Deutsch](README.de.md) · [Русский](README.ru.md) · [Français](README.fr.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Português (Brasil)](README.pt-BR.md) · [Polski](README.pl.md) · [Українська](README.uk.md) · [日本語](README.ja.md) · [简体中文](README.zh-CN.md)

</div>

# PicardWulf v1.0

**MusicBrainz Picard 3.0 用の複数サービス横断リリース検索、自動メタデータ選択、安全なタグ保存。**

> **状態:** リリース候補。ローカルテストは成功しましたが、BMAX-B6 上でのプラグイン起動、実際の API 応答、音楽ファイルへの保存は未検証です。

## 主な機能

- MusicBrainz、Deezer、Apple/iTunes を検索。Spotify、SoundCloud、Last.fm は正規の API 認証情報がある場合に利用できます。
- **フォルダーを追加**すると、曲名・アーティスト・アルバム・再生時間・ISRC・識別子で候補を比較します。
- **最も高い信頼スコアのリリースを選択**します。MusicBrainz を優先せず、Deezer や Spotify なども勝者になれます。
- 異なる版や識別子の衝突、僅差の候補は自動適用せず、手動確認に回します。
- Picard 標準のアルバム欄に読み込めるのは、検証済み MusicBrainz Release/Recording MBID のみです。外部サービスの ID を偽の MBID として使用しません。
- 自動選択は原則として Picard 内のメタデータだけを変更します。**音声ファイルの自動保存は初期状態で無効**です。明示的に有効化した場合、保存前にファイル全体をバックアップし SHA-256 で検証します。
- NEOWULF のファイル名ルールを保持します。単独アーティストのコンピレーションを誤って Various Artists に分類せず、*Curtain Call 2* は Eminem とします。

## Windows でのインストール

Picard **3.0** を終了し、パッケージを展開して、デスクトップのユーザー（BMAX-B6 では `megal`）で **`Install-NEOWULF.cmd`** を実行します。保存先は `%APPDATA%\MusicBrainz\Picard\plugins3\neowulf_picard_repair` です。問題のある `picard-cli.exe` は使いません。その後 **Options → Plugins** で有効化してください。

## 操作と注意事項

**File → Add Folder** で検索が始まります。**Tools → PicardWulf** で候補とバックアップ付き保存を確認でき、**Tools → NEOWULF** でソース状況と命名修復を扱えます。自動適用には、原則として **93.5% 以上**の明確な一致が必要です。検索内容は有効なサービスに送信され、各 API の規約と制限が適用されます。Windows の実動作検証は未完了です。

## 開発

```bash
python -m unittest discover -s tests -v
```

[英語の詳細ドキュメント](README.md) · [変更履歴](CHANGELOG.md) · [作業状況](LAST_TASKS.md) · [ライセンス](LICENSE)
