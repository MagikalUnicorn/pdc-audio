# PDC-Audio

PDC-Audio recovers and decodes the `SEMC PDC-AUDIO` object embedded in supported
NTT DoCoMo MOVA video recordings. Decoded audio is mono, 8 kHz, signed 16-bit
PCM.

The utility can also create a new playable ASF containing the original MJPEG
video packets, decoded PCM audio, and the original proprietary descriptor. It
never modifies the source recording in place.

## Status

The decoder is the audited floating-point v3 core with the v3.3 ASF-preserving
workflow. It is a strong implementation of the error-free PDC half-rate /
PSI-CELP equations, but it is not claimed to be bit-exact with the unavailable
historical fixed-point reference implementation.

The command-line interface is model-neutral. It accepts any MOVA ASF carrying
the validated `SEMC PDC-AUDIO` descriptor, 16-byte object header, and 24-byte
record layout. Active records are accepted by CRC rather than a device-specific
trailer whitelist. The supplied test corpus is from Sony Ericsson SO505i
recordings; other MOVA manufacturers or containers may use different private
storage and require an additional parser.

## Repository layout

```text
src/pdc_audio/   importable decoder and ASF tooling
scripts/         portable Python build, test, and run helpers
tests/           media-independent core tests and ASF integration test
docs/            development instructions and historical technical audits
```

Standards, locally generated decoder tables, private recordings, and generated
media are deliberately kept outside Git in the sibling `pdc-audio-media`
directory.

## Standards and references

The decoder and its conformance audits are based on these supplied references:

1. Association of Radio Industries and Businesses (ARIB), *Personal Digital
   Cellular Telecommunication System*, RCR STD-27 L, Fascicle 2, Revision L,
   30 November 2005, English translation. This is the normative source for the
   PDC half-rate speech-decoder equations, bit mappings, CRC, codebooks, and
   synthesis procedure used by the implementation.
2. Association of Radio Industries and Businesses (ARIB), *Personal Digital
   Cellular Telecommunication System: Quality Recommendation and Validation
   Test for Speech Codec—Standard Technical Characteristics and Validation
   Testing Methods Related to Speech Codec Connectivity and Speech Quality*,
   ARIB TR-T1 Rev. 1.1, 25 July 2000, English translation. This describes codec
   validation and the historical fixed-point master-codec/reference-file
   process underlying the remaining bit-exactness limitations.
3. Satoshi Miki, Kazunori Mano, Takehiro Moriya, Kumiko Oguchi, and Hitoshi
   Ohmuro, “A Pitch Synchronous Innovation CELP (PSI-CELP) Coder for 2–4
   kbit/s,” *Proceedings of ICASSP 1994*, vol. II, pp. II-113–II-116. This
   provides technical background on the pitch-synchronous innovation method
   used by the PDC half-rate codec.

Local copies are expected under `../pdc-audio-media/standards` with the supplied
filenames `ARIB PDC RCR STD-27 L.pdf`, `ARIB PDC RCR STD-27 TR-T01 v1.pdf`, and
`NTT PSI-CELP Paper.pdf`. They remain outside the repository because of their
copyright and redistribution terms. See [the core audit](docs/CORE_AUDIT.md)
and [the final audit](docs/FINAL_CORE_AUDIT.md) for equation-level use of these
references.

ARIB publishes the supported Fascicle 2 PDF from its
[RCR STD-27 page](https://www.arib.or.jp/english/std_tr/telecommunications/std-27.html).
The table generator supports the official English Revision L
[Fascicle 2 PDF](https://www.arib.or.jp/english/html/overview/doc/5-STD-27_L-2p3-E.pdf)
whose SHA-256 is
`d45bf76f02e3fbb927150e104a608c8fcee5015efd140323d820dd6505a703fb`.
Public availability does not make the document or its tables part of this
project's MIT licence; see [ARIB's copyright notice](https://www.arib.or.jp/english/std_tr/index.html).

## Requirements and build

PDC-Audio requires Python 3.11 or later and NumPy. Poppler's `pdftotext` is
needed once to generate the decoder tables. FFmpeg is needed only for ASF or
MP4 output; decoding to WAV does not require it.

In MSYS2 MinGW64, install the dependencies once:

```console
pacman -S --needed mingw-w64-x86_64-python-numpy \
    mingw-w64-x86_64-python-pip mingw-w64-x86_64-python-setuptools \
    mingw-w64-x86_64-python-build mingw-w64-x86_64-poppler \
    mingw-w64-x86_64-ffmpeg
```

### Generate the decoder tables locally

The ARIB codebook tables are not included in this repository, its Git history,
or its wheel. Download the supported official Fascicle 2 PDF above and keep it
under `../pdc-audio-media/standards`. From the repository root, generate your
local table file:

```console
python scripts/generate_arib_tables.py \
    "../pdc-audio-media/standards/ARIB PDC RCR STD-27 L.pdf"
```

The helper verifies the PDF's SHA-256, extracts the required tables with
`pdftotext`, checks their canonical numerical digest, and writes
`../pdc-audio-media/generated/arib_std27_tables.npz`. The source PDF and the
generated file remain outside Git. This step is required once before running
or testing the decoder; rerun it if the generated file is removed.

Then build the project from the repository root:

```console
python scripts/build.py
```

The helper creates `.venv`, installs the project in editable mode, and builds a
wheel under `dist`.

### Running from Windows PowerShell

From the repository root in PowerShell, use the MSYS2 Python executable
explicitly. This avoids the Windows Microsoft Store `python` alias when MSYS2
is not on PowerShell's `PATH`. These commands invoke the portable Python
helpers; no PowerShell scripts are required.

Build the project:

```powershell
& "C:\msys64\mingw64\bin\python.exe" .\scripts\build.py
```

Before the first run or test, generate the local decoder tables from the
supported PDF:

```powershell
& "C:\msys64\mingw64\bin\python.exe" .\scripts\generate_arib_tables.py `
    "..\pdc-audio-media\standards\ARIB PDC RCR STD-27 L.pdf"
```

List the available external ASF recordings:

```powershell
Get-ChildItem ..\pdc-audio-media\samples\*.asf
```

Decode one recording to WAV, replacing `your-recording.asf` with its filename:

```powershell
& "C:\msys64\mingw64\bin\python.exe" .\scripts\convert_mova_pdc_audio.py `
    "..\pdc-audio-media\samples\your-recording.asf" `
    --wav "..\pdc-audio-media\outputs\decoded.wav"
```

To create a verified ASF with an automatically generated timestamped filename,
omit the output options:

```powershell
& "C:\msys64\mingw64\bin\python.exe" .\scripts\convert_mova_pdc_audio.py `
    "..\pdc-audio-media\samples\your-recording.asf"
```

Automatic ASF output is written under `..\pdc-audio-media\outputs`. Quote paths
that contain spaces. Existing output files are not replaced unless `--force`
is supplied deliberately.

## Run

Create a verified ASF in the external output directory:

```console
python scripts/convert_mova_pdc_audio.py \
    ../pdc-audio-media/samples/sample.asf
```

Choose outputs explicitly when required:

```console
python scripts/convert_mova_pdc_audio.py \
    ../pdc-audio-media/samples/sample.asf \
    --asf ../pdc-audio-media/outputs/decoded.asf \
    --wav ../pdc-audio-media/outputs/decoded.wav \
    --json ../pdc-audio-media/outputs/parameters.json
```

Useful options include `--float-npy`, `--mp4`, `--no-normalize`, `--force`,
`--ffmpeg PATH`, and `--tables PATH`. ASF output verifies the copied video
packets, decoded PCM, and preserved binary descriptor by default;
`--no-verify` disables that pass. The helpers use the external generated table
path automatically. For an installed command outside this checkout, either
pass `--tables PATH` or set the `PDC_AUDIO_TABLES` environment variable.

The installed `pdc-audio` command provides the same decoder interface. Lower
level commands are also installed:

- `pdc-audio-extract` extracts the proprietary object from an ASF.
- `pdc-audio-decode-records` decodes an extracted sequence of 24-byte records.
- `pdc-audio-preserve` copies the descriptor into an already-remuxed ASF.

## Test

Run the core suite and every external ASF sample:

```console
python scripts/test.py
```

Run only media-independent tests with `python scripts/test.py --unit-only`.
See [the development instructions](docs/DEVELOPMENT.md) for all helper options
and the repository’s private-media rules.

## Imported development history

The four supplied archives were imported as distinct development snapshots
before the repository was reorganised. Redistribution-sensitive decoder table
data has been removed from every revision and tag. The snapshots can be
inspected with these tags:

- `snapshot-v2`
- `snapshot-v3-core-audit`
- `snapshot-v3.2-final-audit`
- `snapshot-v3.3-final-asf`

See [the core audit](docs/CORE_AUDIT.md),
[the final audit](docs/FINAL_CORE_AUDIT.md),
[v3.3 validation](docs/VALIDATION.md), and
[the FFmpeg integration assessment](docs/FFMPEG_INTEGRATION.md) for technical
detail and known limitations.

## License

PDC-Audio source code and repository documentation are available under the
[MIT License](LICENSE). External standards and papers are not included in the
repository and remain subject to their respective copyright and distribution
terms. Locally generated table files are derived from the user's copy of the
ARIB standard, are not covered by this project's MIT licence, and should not be
committed or redistributed as part of this repository.

## 日本語

### 概要

PDC-Audio は、対応する NTT ドコモ MOVA の動画ファイルに埋め込まれた
`SEMC PDC-AUDIO` オブジェクトを取り出し、音声を復号するためのツールです。
復号後の音声は、モノラル、8 kHz、符号付き 16 ビット PCM です。

元の MJPEG 映像、復号した PCM 音声、および独自形式の記述子を含む、再生可能な
ASF ファイルも作成できます。元の録画ファイルを直接変更することはありません。

コマンドラインは特定の機種名やファイル名に依存しません。現在対応しているのは、
検証済みの `SEMC PDC-AUDIO` 記述子、16 バイトのオブジェクトヘッダー、および
24 バイトのレコード構造を持つ MOVA の ASF ファイルです。付属のテスト用データは
Sony Ericsson SO505i で録画されたものです。他社製 MOVA 端末や別のコンテナ形式では、
追加の解析処理が必要になる場合があります。

### 必要環境とビルド

Python 3.11 以降と NumPy が必要です。復号テーブルを一度生成するために、Poppler の
`pdftotext` も必要です。WAV への復号だけであれば FFmpeg は不要です。ASF または
MP4 を出力する場合には FFmpeg が必要です。

MSYS2 MinGW64 では、最初に依存パッケージをインストールします。

```console
pacman -S --needed mingw-w64-x86_64-python-numpy \
    mingw-w64-x86_64-python-pip mingw-w64-x86_64-python-setuptools \
    mingw-w64-x86_64-python-build mingw-w64-x86_64-poppler \
    mingw-w64-x86_64-ffmpeg
```

### 復号テーブルのローカル生成

ARIB のコードブック表は、このリポジトリ、Git 履歴、および wheel には含まれません。
上記の ARIB 公式ページから対応する英語版 Revision L Fascicle 2 PDF を取得し、
`../pdc-audio-media/standards` に保存してください。リポジトリのルートで次を実行します。

```console
python scripts/generate_arib_tables.py \
    "../pdc-audio-media/standards/ARIB PDC RCR STD-27 L.pdf"
```

ヘルパーは PDF の SHA-256 を確認し、`pdftotext` で必要な表を抽出し、数値内容の
整合性を検証した後、`../pdc-audio-media/generated/arib_std27_tables.npz` を作成します。
PDF と生成ファイルは Git の外部に置かれます。復号またはテストの前に一度必要な
手順であり、生成ファイルを削除した場合は再実行してください。

リポジトリのルートで次のコマンドを実行すると、`.venv` の作成、編集可能モードでの
インストール、および `dist` ディレクトリへの wheel の作成が行われます。

```console
python scripts/build.py
```

### Windows PowerShell からの実行

PowerShell では `python` が Microsoft Store のエイリアスとして解決される場合が
あるため、リポジトリのルートから MSYS2 の Python を明示的に指定してください。
以下のコマンドは Python ヘルパーを実行するもので、PowerShell スクリプトは使用しません。

プロジェクトをビルドします。

```powershell
& "C:\msys64\mingw64\bin\python.exe" .\scripts\build.py
```

初回の実行またはテストの前に、対応する PDF から復号テーブルを生成します。

```powershell
& "C:\msys64\mingw64\bin\python.exe" .\scripts\generate_arib_tables.py `
    "..\pdc-audio-media\standards\ARIB PDC RCR STD-27 L.pdf"
```

外部ディレクトリにある ASF 録画ファイルを確認します。

```powershell
Get-ChildItem ..\pdc-audio-media\samples\*.asf
```

`your-recording.asf` を実際のファイル名に置き換え、WAV に復号します。

```powershell
& "C:\msys64\mingw64\bin\python.exe" .\scripts\convert_mova_pdc_audio.py `
    "..\pdc-audio-media\samples\your-recording.asf" `
    --wav "..\pdc-audio-media\outputs\decoded.wav"
```

出力オプションを省略すると、タイムスタンプ付きのファイル名で検証済み ASF を作成します。

```powershell
& "C:\msys64\mingw64\bin\python.exe" .\scripts\convert_mova_pdc_audio.py `
    "..\pdc-audio-media\samples\your-recording.asf"
```

自動生成した ASF は `..\pdc-audio-media\outputs` に保存されます。空白を含むパスは
引用符で囲んでください。既存の出力ファイルは、`--force` を明示的に指定しない限り
上書きされません。

### 実行方法

外部の出力ディレクトリに、検証済みの ASF ファイルを作成します。

```console
python scripts/convert_mova_pdc_audio.py \
    ../pdc-audio-media/samples/sample.asf
```

出力先を個別に指定する場合は、次のように実行します。

```console
python scripts/convert_mova_pdc_audio.py \
    ../pdc-audio-media/samples/sample.asf \
    --asf ../pdc-audio-media/outputs/decoded.asf \
    --wav ../pdc-audio-media/outputs/decoded.wav \
    --json ../pdc-audio-media/outputs/parameters.json
```

インストール後は `pdc-audio` コマンドでも同じ機能を利用できます。
通常、Python ヘルパーは外部の生成済みテーブルを自動的に使用します。別の場所に
保存した場合は `--tables PATH` を指定してください。チェックアウト外でインストール済み
コマンドを使う場合は、`--tables PATH` または環境変数 `PDC_AUDIO_TABLES` を使用できます。

### テスト

ユニットテストと、外部ディレクトリにあるすべての ASF サンプルに対する結合テストを
実行します。

```console
python scripts/test.py
```

録画ファイルを使用しないテストだけを実行する場合は、
`python scripts/test.py --unit-only` を使用してください。

### 規格文書と録画ファイル

実装は、上記の「Standards and references」に記載した RCR STD-27 L、ARIB TR-T1、
および PSI-CELP 論文を参照しています。これらの規格文書、個人の録画ファイル、画像、
抽出データ、および生成した音声・動画は Git に追加せず、隣接する
`../pdc-audio-media` ディレクトリに保存してください。

対応する PDF は ARIB の公式 RCR STD-27 ページから公開されていますが、公開されている
こと自体は MIT ライセンスを意味しません。復号テーブルは利用者自身の PDF からローカルで
生成し、Git や配布用 wheel には含めないでください。

### ライセンス

PDC-Audio のソースコードおよびリポジトリ内の文書は、
[MIT License](LICENSE) の下で公開されています。外部の規格文書および論文は
リポジトリに含まれず、それぞれの著作権および配布条件が適用されます。ローカルで
生成したテーブルファイルは本プロジェクトの MIT ライセンスの対象ではなく、この
リポジトリの一部としてコミットまたは再配布しないでください。
