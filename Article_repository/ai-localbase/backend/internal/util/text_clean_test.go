package util

import (
	"strings"
	"testing"
)

// 预处理质量优化：HTML 标签/实体、控制字符、模板化噪声行都应被清理。
func TestCleanDocumentTextRemovesNoise(t *testing.T) {
	input := strings.Join([]string{
		"<html><head><title>x</title></head><body>",
		"<script>var a = 1;</script>",
		"<p>Autism &amp; gut microbiota&#160;differ significantly.</p>",
		"Downloaded from https://example.org on 2026-09-01",
		"All rights reserved.",
		"Copyright \u00a9 2026 Elsevier",
		"</body></html>",
	}, "\n")

	cleaned, stats := CleanDocumentText(input)

	for _, banned := range []string{"<html", "<script", "</p>", "&amp;", "&#160;", "Downloaded from", "All rights reserved"} {
		if strings.Contains(cleaned, banned) {
			t.Errorf("cleaned text still contains %q:\n%s", banned, cleaned)
		}
	}
	if !strings.Contains(cleaned, "Autism & gut microbiota") {
		t.Errorf("expected decoded entity text, got:\n%s", cleaned)
	}
	// 换行实体 &#160; 解码为非换行空格，随后应归一为普通空格
	if strings.Contains(cleaned, "\u00a0") {
		t.Errorf("expected nbsp to be normalized to space, got %q", cleaned)
	}
	if stats.HTMLTagsRemoved == 0 {
		t.Errorf("expected html tags removal count > 0, got %+v", stats)
	}
	if stats.HTMLEntitiesFixed == 0 {
		t.Errorf("expected html entity count > 0, got %+v", stats)
	}
	if stats.BoilerplateLines < 3 {
		t.Errorf("expected >=3 boilerplate lines dropped, got %d", stats.BoilerplateLines)
	}
}

// 全角标点是中文正文内容，且结构化摘要标记依赖全角冒号，不能被转成半角。
func TestCleanDocumentTextPreservesFullWidthPunctuation(t *testing.T) {
	input := "统计摘要：共 3 行\n第1行：a,b\n第2行：c,d\n第3行：e,f"
	cleaned, _ := CleanDocumentText(input)

	if !strings.Contains(cleaned, "统计摘要：") {
		t.Fatalf("full-width colon was destroyed:\n%s", cleaned)
	}
	if !strings.Contains(cleaned, "第1行：") {
		t.Fatalf("full-width colon in row marker was destroyed:\n%s", cleaned)
	}
	if strings.Contains(cleaned, "统计摘要:") {
		t.Fatalf("full-width colon should NOT be converted to half-width:\n%s", cleaned)
	}
}

// 全角字母数字仍应转半角，便于与检索词对齐。
func TestCleanDocumentTextNormalizesFullWidthAlnum(t *testing.T) {
	cleaned, stats := CleanDocumentText("ＡＢＣ１２３ ｔｅｓｔ，保留全角逗号")
	if !strings.Contains(cleaned, "ABC123") {
		t.Errorf("expected full-width alnum to be normalized, got:\n%s", cleaned)
	}
	if !strings.Contains(cleaned, "test") {
		t.Errorf("expected full-width latin to be normalized, got:\n%s", cleaned)
	}
	if !strings.Contains(cleaned, "，") {
		t.Errorf("expected full-width comma preserved, got:\n%s", cleaned)
	}
	if stats.UnicodeNormalized == 0 {
		t.Errorf("expected unicode normalization count > 0")
	}
}

// 控制字符与零宽字符必须被剔除。
func TestCleanDocumentTextRemovesControlRunes(t *testing.T) {
	input := "alpha\u200bbeta\u0007gamma\ufeffdelta\u202e"
	cleaned, stats := CleanDocumentText(input)
	if cleaned != "alphabetagammadelta" {
		t.Errorf("unexpected cleaned text: %q", cleaned)
	}
	if stats.ControlRunesDrop != 4 {
		t.Errorf("expected 4 control runes dropped, got %d", stats.ControlRunesDrop)
	}
}

// 尾部参考文献列表应被裁掉（位于文档后段且其后仍有可观内容）。
func TestCleanDocumentTextTrimsReferences(t *testing.T) {
	body := make([]string, 0, 40)
	for i := 0; i < 20; i++ {
		body = append(body, "Autism spectrum disorder is associated with altered gut microbiota composition in children.")
	}
	refs := []string{"References"}
	for i := 0; i < 20; i++ {
		refs = append(refs, "Smith J, et al. A study of the gut microbiome in autism. Nature. 2020;12(3):123-130.")
	}
	input := strings.Join(append(body, refs...), "\n")

	cleaned, stats := CleanDocumentText(input)
	if !stats.ReferencesTrimmed {
		t.Fatalf("expected references section to be trimmed")
	}
	if strings.Contains(cleaned, "Smith J, et al.") {
		t.Errorf("reference entries should be removed:\n%s", cleaned)
	}
	if !strings.Contains(cleaned, "Autism spectrum disorder") {
		t.Errorf("body text should be preserved")
	}
}

// 正文提到 References 但位于文档前段时不应裁剪。
func TestCleanDocumentTextKeepsEarlyReferencesMention(t *testing.T) {
	var lines []string
	lines = append(lines, "References")
	for i := 0; i < 40; i++ {
		lines = append(lines, "Body paragraph that discusses the topic in detail with enough characters to count.")
	}
	cleaned, stats := CleanDocumentText(strings.Join(lines, "\n"))
	if stats.ReferencesTrimmed {
		t.Errorf("early 'References' line should not trigger trimming")
	}
	if !strings.Contains(cleaned, "References") {
		t.Errorf("early mention should be preserved")
	}
}

func TestCleanDocumentTextEmpty(t *testing.T) {
	cleaned, stats := CleanDocumentText("   \n\n\t  ")
	if cleaned != "" {
		t.Errorf("expected empty output, got %q", cleaned)
	}
	if stats.OriginalRunes == 0 {
		t.Errorf("expected original rune count recorded")
	}
}

func TestIsStopword(t *testing.T) {
	for _, token := range []string{"the", "THE", "and", "of", "的", "了", "在"} {
		if !IsStopword(token) {
			t.Errorf("expected %q to be a stopword", token)
		}
	}
	for _, token := range []string{"autism", "microbiota", "asd", "菌群", "16S", ""} {
		if token == "" {
			continue
		}
		if IsStopword(token) {
			t.Errorf("expected %q NOT to be a stopword", token)
		}
	}
}

func TestFilterStopwords(t *testing.T) {
	got := FilterStopwords([]string{"the", "gut", "and", "microbiota", "的", "菌"})
	want := []string{"gut", "microbiota", "菌"}
	if len(got) != len(want) {
		t.Fatalf("got %v, want %v", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("got %v, want %v", got, want)
		}
	}
}

// 停用词过多时仍应保留原始 token，避免稀疏通道退化为空向量。
func TestFilterStopwordsAllStopwords(t *testing.T) {
	got := FilterStopwords([]string{"the", "and", "of"})
	if len(got) != 0 {
		t.Fatalf("expected all stopwords filtered, got %v", got)
	}
}

func TestStripHTMLKeepsMathComparisons(t *testing.T) {
	// p < 0.05 不是标签，不能被吞掉
	cleaned, _ := StripHTML("<p>p < 0.05 and a < b were significant</p>")
	if !strings.Contains(cleaned, "p < 0.05") {
		t.Errorf("math comparison was destroyed:\n%s", cleaned)
	}
	if !strings.Contains(cleaned, "a < b") {
		t.Errorf("math comparison was destroyed:\n%s", cleaned)
	}
	if strings.Contains(cleaned, "<p>") {
		t.Errorf("html tag should be removed:\n%s", cleaned)
	}
}
