<div align="center">

[English](README.md) · [Deutsch](README.de.md) · [Русский](README.ru.md) · [Français](README.fr.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Português (Brasil)](README.pt-BR.md) · [Polski](README.pl.md) · [Українська](README.uk.md) · [日本語](README.ja.md) · [简体中文](README.zh-CN.md)

</div>

# PicardWulf v1.0

**Busca de lançamentos em múltiplas fontes, seleção automática e gravação segura de tags para MusicBrainz Picard 3.0.**

> **Estado:** versão candidata. Testes locais aprovados; execução no BMAX-B6, acesso real às APIs e gravação de arquivos ainda precisam de validação.

## Recursos

- Consulta MusicBrainz, Deezer e Apple/iTunes, além de Spotify, SoundCloud e Last.fm com credenciais de API autorizadas.
- Após **Adicionar pasta**, classifica lançamentos por título, artista, álbum, duração, ISRC e identificadores comprovados.
- **A fonte com maior pontuação vence**, mesmo quando não é MusicBrainz; Deezer e Spotify podem fornecer o resultado selecionado.
- Lançamentos ambíguos, edições distintas e conflitos de identificação exigem revisão manual.
- Somente MBIDs reais de release/gravação MusicBrainz podem alimentar a janela nativa de álbuns do Picard. IDs de outros serviços permanecem separados.
- A seleção automática atualiza primeiro os metadados dentro do Picard. **Salvar arquivos automaticamente fica desativado** por padrão; após autorização explícita, cada áudio recebe um backup integral verificado por SHA-256.
- Preserva as regras NEOWULF e evita classificar compilações individuais como Various Artists. *Curtain Call 2* permanece com Eminem.

## Instalação

Feche o Picard **3.0**, extraia o pacote e execute **`Install-NEOWULF.cmd`** na conta de desktop (`megal` no BMAX-B6). O plugin fica em `%APPDATA%\MusicBrainz\Picard\plugins3\neowulf_picard_repair`; o `picard-cli.exe` defeituoso não é utilizado. Ative-o em **Options → Plugins**.

## Uso e segurança

**File → Add Folder** inicia a busca. **Tools → PicardWulf** permite revisar a classificação e habilitar a gravação com backup; **Tools → NEOWULF** mostra fontes e reparo de nomes. A aplicação automática exige pontuação inequívoca de pelo menos **93,5 %**. Os termos de busca são enviados aos provedores habilitados, respeitando limites e permissões. A validação prática no Windows ainda está pendente.

## Desenvolvimento

```bash
python -m unittest discover -s tests -v
```

[Documentação detalhada em inglês](README.md) · [Alterações](CHANGELOG.md) · [Estado](LAST_TASKS.md) · [Licença](LICENSE)
