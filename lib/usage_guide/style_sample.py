# -*- coding: utf-8 -*-

# auth_portal_app/lib/usage_guide/style_sample.py

# ============================================================
# PAIS使い方ガイド：スタイル見本
#
# 機能：
# - 使い方ガイドで使用する共通スタイルの表示見本を定義する
# - styles.py に定義した各スタイルを一覧で確認できるようにする
# - 各スタイルの実際の記述方法も画面上で確認できるようにする
#
# 方針：
# - 描画処理は持たない
# - styles.py に定義された class 名だけを使用する
# - InfoPanel として PAISについて に登録する
# - 記述例は <pre><code> を使用して安全に表示する
# ============================================================

from __future__ import annotations


# ============================================================
# imports
# ============================================================

from .models import (
    GuideSection,
    InfoPanel,
)


# ============================================================
# スタイル見本
# ============================================================

INFO_USAGE_GUIDE_STYLE_SAMPLE = InfoPanel(
    key="usage_guide_style_sample",
    title="使い方ガイド：スタイル見本（開発用）",
    icon="🎨",
    summary="使い方ガイドで使用する共通スタイルの表示見本です．",
    sections=(

        # ====================================================
        # ブロック表示
        # ====================================================
        GuideSection(
            title="ブロック表示",
            body="""

### 小さい補足文字

#### 表示例

<div class="guide-small">
これは補足説明などに使用する，小さい文字の表示です．
</div>

#### 書き方

<pre><code>&lt;div class="guide-small"&gt;
これは補足説明などに使用する，小さい文字の表示です．
&lt;/div&gt;</code></pre>


---

### 手順内の補足行

#### 表示例

<div class="guide-substep">
- チャンク長：15分<br>
- オーバーラップ：1分
</div>

#### 書き方

<pre><code>&lt;div class="guide-substep"&gt;
- チャンク長：15分&lt;br&gt;
- オーバーラップ：1分
&lt;/div&gt;</code></pre>

""",
        ),

        # ====================================================
        # インライン表示
        # ====================================================
        GuideSection(
            title="インライン表示",
            body="""

### 画面遷移・補足表示

#### 表示例

<div class="guide-note">
    <span class="guide-route">ミニッツメーカー ▶ タイムスタンプ付きの文字起こし</span><br><br>
    <span class="guide-small">
    サイドバーでモデルを指定します．通常はデフォルト設定のまま使用します．<br>
    <span class="guide-indent">・gpt-4o-transcribe-diarize（デフォルトのタイムスタンプ付き文字起こしモデル）</span><br>
    </span>
</div>

#### 書き方

<pre><code>&lt;div class="guide-note"&gt;
    &lt;span class="guide-route"&gt;ミニッツメーカー ▶ タイムスタンプ付きの文字起こし&lt;/span&gt;&lt;br&gt;&lt;br&gt;
    &lt;span class="guide-small"&gt;
    サイドバーでモデルを指定します．通常はデフォルト設定のまま使用します．&lt;br&gt;
    &lt;span class="guide-indent"&gt;・gpt-4o-transcribe-diarize（デフォルトのタイムスタンプ付き文字起こしモデル）&lt;/span&gt;&lt;br&gt;
    &lt;/span&gt;
&lt;/div&gt;</code></pre>


---

### guide-route

#### 表示例

<span class="guide-route">ミニッツメーカー ▶ タイムスタンプ付きの文字起こし</span>

#### 書き方

<pre><code>&lt;span class="guide-route"&gt;ミニッツメーカー ▶ タイムスタンプ付きの文字起こし&lt;/span&gt;</code></pre>


---

### guide-small

#### 表示例

<span class="guide-small">
これは補足説明などに使用する，小さい文字です．
</span>

#### 書き方

<pre><code>&lt;span class="guide-small"&gt;
これは補足説明などに使用する，小さい文字です．
&lt;/span&gt;</code></pre>


---

### guide-indent

#### 表示例

<span class="guide-small">
サイドバーでモデルを指定します．<br>
<span class="guide-indent">・gpt-4o-transcribe-diarize</span><br>
<span class="guide-indent">・whisper-1</span>
</span>

#### 書き方

<pre><code>&lt;span class="guide-small"&gt;
サイドバーでモデルを指定します．&lt;br&gt;
&lt;span class="guide-indent"&gt;・gpt-4o-transcribe-diarize&lt;/span&gt;&lt;br&gt;
&lt;span class="guide-indent"&gt;・whisper-1&lt;/span&gt;
&lt;/span&gt;</code></pre>

""",
        ),

        # ====================================================
        # 操作手順
        # ====================================================
        GuideSection(
            title="操作手順",
            body="""

            
---

### guide-model-green

AIモデル名などを本文中で強調して表示する場合に使用します．

#### 表示例

文字起こしのAIが
<span class="guide-model-green">gpt-4o-transcribe-diarize</span>
に限られます．

#### 書き方

<pre><code>文字起こしのAIが
&lt;span class="guide-model-green"&gt;gpt-4o-transcribe-diarize&lt;/span&gt;
に限られます．</code></pre>


---

### 通常の操作手順

#### 表示例

① 音声ファイルを設定します．  
② サイドバーでモデルを設定します．  
③ 「文字起こしを実行+ストレージ保存」を押します．

#### 書き方

<pre><code>① 音声ファイルを設定します．
② サイドバーでモデルを設定します．
③ 「文字起こしを実行+ストレージ保存」を押します．</code></pre>


---

### 手順の途中に補足を入れる場合

#### 表示例

① 音声ファイルを設定します．

<div class="guide-substep">
- 対応形式：mp3，wav，m4a<br>
- 通常はそのままアップロードします．
</div>

② サイドバーでモデルを設定します．

<div class="guide-substep">
- 通常はデフォルト設定のまま使用します．
</div>

③ 「文字起こしを実行+ストレージ保存」を押します．

#### 書き方

<pre><code>① 音声ファイルを設定します．

&lt;div class="guide-substep"&gt;
- 対応形式：mp3，wav，m4a&lt;br&gt;
- 通常はそのままアップロードします．
&lt;/div&gt;

② サイドバーでモデルを設定します．

&lt;div class="guide-substep"&gt;
- 通常はデフォルト設定のまま使用します．
&lt;/div&gt;

③ 「文字起こしを実行+ストレージ保存」を押します．</code></pre>

""",
        ),

        # ====================================================
        # 手順内の小見出し
        # ====================================================
        GuideSection(
            title="手順内の小見出し",
            body="""

### 通常の文章

#### 表示例

最初に，会議などの音声ファイルを
『音声ファイル分割』
で処理します．

#### 書き方

<pre><code>最初に，会議などの音声ファイルを
『音声ファイル分割』
で処理します．</code></pre>


---

### 小見出しの下に補足を入れる場合

#### 表示例

最初に，会議などの音声ファイルを
『音声ファイル分割』
で処理します．

<div class="guide-substep">
- チャンク長：15分<br>
- オーバーラップ：1分<br>
- 通常はデフォルト設定のまま使用します．
</div>

#### 書き方

<pre><code>最初に，会議などの音声ファイルを
『音声ファイル分割』
で処理します．

&lt;div class="guide-substep"&gt;
- チャンク長：15分&lt;br&gt;
- オーバーラップ：1分&lt;br&gt;
- 通常はデフォルト設定のまま使用します．
&lt;/div&gt;</code></pre>

""",
        ),

        # ====================================================
        # 色付きパネル
        # ====================================================
        GuideSection(
            title="色付きパネル",
            body="""

### グレー

既存の `guide-note` と同じ色です．

#### 表示例

<div class="guide-gray">
グレーのパネルです．補足情報などに使用できます．
</div>

#### 書き方

<pre><code>&lt;div class="guide-gray"&gt;
グレーのパネルです．補足情報などに使用できます．
&lt;/div&gt;</code></pre>


---

### グリーン

既存の `guide-point` と同じ色です．

#### 表示例

<div class="guide-green">
グリーンのパネルです．重要ポイントなどに使用できます．
</div>

#### 書き方

<pre><code>&lt;div class="guide-green"&gt;
グリーンのパネルです．重要ポイントなどに使用できます．
&lt;/div&gt;</code></pre>


---

### イエロー

既存の `guide-warning` と同じ色です．

#### 表示例

<div class="guide-yellow">
イエローのパネルです．注意事項などに使用できます．
</div>

#### 書き方

<pre><code>&lt;div class="guide-yellow"&gt;
イエローのパネルです．注意事項などに使用できます．
&lt;/div&gt;</code></pre>


---

### ブルー

#### 表示例

<div class="guide-blue">
ブルーのパネルです．情報や案内などに使用できます．
</div>

#### 書き方

<pre><code>&lt;div class="guide-blue"&gt;
ブルーのパネルです．情報や案内などに使用できます．
&lt;/div&gt;</code></pre>


---

### レッド

#### 表示例

<div class="guide-red">
レッドのパネルです．特に重要な注意事項などに使用できます．
</div>

#### 書き方

<pre><code>&lt;div class="guide-red"&gt;
レッドのパネルです．特に重要な注意事項などに使用できます．
&lt;/div&gt;</code></pre>


---

### 既存クラス

既存のガイドでは，以下のクラスをそのまま使用できます．

#### guide-note

<div class="guide-note">
既存の guide-note です．guide-gray と同じ色です．
</div>

<pre><code>&lt;div class="guide-note"&gt;
既存の guide-note です．
&lt;/div&gt;</code></pre>


#### guide-point

<div class="guide-point">
既存の guide-point です．guide-green と同じ色です．
</div>

<pre><code>&lt;div class="guide-point"&gt;
既存の guide-point です．
&lt;/div&gt;</code></pre>


#### guide-warning

<div class="guide-warning">
既存の guide-warning です．guide-yellow と同じ色です．
</div>

<pre><code>&lt;div class="guide-warning"&gt;
既存の guide-warning です．
&lt;/div&gt;</code></pre>

""",
        ),

    ),
)