package util

import (
	"strings"
	"testing"
)

// 递归切分应优先在**段落**边界断开，而不是按字数硬切。
func TestSplitRecursiveUsesParagraphBoundaryFirst(t *testing.T) {
	p1 := "第一段的内容比较长，需要单独成块。"
	p2 := "第二段的内容也比较长，需要单独成块。"
	text := p1 + "\n\n" + p2

	got := SplitRecursiveBySemanticUnits(text, 30)

	if len(got) != 2 {
		t.Fatalf("expected 2 chunks split at the paragraph boundary, got %d: %q", len(got), got)
	}
	if got[0] != p1 || got[1] != p2 {
		t.Fatalf("chunks should follow paragraph boundaries exactly, got %q", got)
	}
}

// 任何不超过上限的块都必须以句子边界收尾 —— 即"不切断句子"。
func TestSplitRecursiveNeverBreaksSentence(t *testing.T) {
	text := "First sentence here. Second sentence here. Third sentence here."

	got := SplitRecursiveBySemanticUnits(text, 30)

	if len(got) < 2 {
		t.Fatalf("expected multiple chunks, got %q", got)
	}
	for _, chunk := range got {
		if runeCount(chunk) > 30 {
			t.Errorf("chunk exceeds limit: %d > 30 (%q)", runeCount(chunk), chunk)
		}
		if !endsWithSentenceTerminator(chunk) {
			t.Errorf("chunk does not end at a sentence boundary: %q", chunk)
		}
	}
}

// 单句超长且无句末标点时，应下探到**子句**边界，不得把单词劈开。
func TestSplitRecursiveDescendsToClauseBoundary(t *testing.T) {
	text := "alpha, beta, gamma, delta, epsilon, zeta, eta, theta, iota, kappa"

	got := SplitRecursiveBySemanticUnits(text, 20)

	if len(got) < 2 {
		t.Fatalf("expected multiple chunks, got %q", got)
	}
	for _, chunk := range got {
		if runeCount(chunk) > 20 {
			t.Errorf("chunk exceeds limit: %d > 20 (%q)", runeCount(chunk), chunk)
		}
	}
	assertNoWordWasSplit(t, text, got)
}

// 完全没有标点时，退化为按空白切分，同样不得切断单词。
func TestSplitRecursiveAlignsToWordBoundary(t *testing.T) {
	text := "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda"

	got := SplitRecursiveBySemanticUnits(text, 20)

	for _, chunk := range got {
		if runeCount(chunk) > 20 {
			t.Errorf("chunk exceeds limit: %d > 20 (%q)", runeCount(chunk), chunk)
		}
	}
	assertNoWordWasSplit(t, text, got)
}

// 单个"词"本身就超限时只能硬切，但不得产生空块。
func TestSplitRecursiveHandlesOversizeSingleWord(t *testing.T) {
	got := SplitRecursiveBySemanticUnits(strings.Repeat("x", 50), 20)

	if len(got) != 3 {
		t.Fatalf("expected 3 windows, got %d: %q", len(got), got)
	}
	for _, chunk := range got {
		if chunk == "" {
			t.Errorf("empty chunk produced")
		}
		if runeCount(chunk) > 20 {
			t.Errorf("chunk exceeds limit: %d (%q)", runeCount(chunk), chunk)
		}
	}
}

// 总长不超限时不应切分。
func TestSplitRecursiveKeepsShortTextWhole(t *testing.T) {
	got := SplitRecursiveBySemanticUnits("短文本。", 100)
	if len(got) != 1 || got[0] != "短文本。" {
		t.Fatalf("short text should stay whole, got %q", got)
	}
	if got := SplitRecursiveBySemanticUnits("   ", 100); got != nil {
		t.Fatalf("blank text should yield nil, got %q", got)
	}
}

// 中文句子之间没有空格，也必须能被切开。
func TestSplitSentencesHandlesChineseWithoutSpaces(t *testing.T) {
	got := splitSentences("第一句。第二句。第三句。", false)

	if len(got) != 3 {
		t.Fatalf("expected 3 Chinese sentences, got %d: %q", len(got), got)
	}
	if got[0] != "第一句。" || got[2] != "第三句。" {
		t.Fatalf("unexpected segmentation: %q", got)
	}
}

// 句末标点后跟哪些字符才算真正的句子边界。
func TestIsSentenceBoundaryAfter(t *testing.T) {
	// 中文标点后紧跟汉字：必须断开（否则中文永远切不出句子）
	if !isSentenceBoundaryAfter('第') {
		t.Error("。 followed by a Han character must be a sentence boundary")
	}
	// 空白：断开
	if !isSentenceBoundaryAfter(' ') {
		t.Error("period followed by space must be a boundary")
	}
	// 闭合引号：断开（引号归属于前一句）
	if !isSentenceBoundaryAfter('”') {
		t.Error("period followed by closing quote must be a boundary")
	}
	// 小数：不断开
	if isSentenceBoundaryAfter('5') {
		t.Error("3.5 must not be treated as a sentence boundary")
	}
	// 缩写：不断开
	if isSentenceBoundaryAfter('g') {
		t.Error("e.g. must not be treated as a sentence boundary")
	}
}

// 归一化必须保留段落分隔（\\n\\n），否则 splitParagraphs 永远切不出段落。
func TestNormalizeChunkTextKeepsParagraphBreaks(t *testing.T) {
	got := normalizeChunkText("第一段。\n\n\n\n第二段。")

	if !strings.Contains(got, "\n\n") {
		t.Fatalf("paragraph break was destroyed: %q", got)
	}
	if paragraphs := splitParagraphs(got); len(paragraphs) != 2 {
		t.Fatalf("expected 2 paragraphs, got %d: %q", len(paragraphs), paragraphs)
	}
}

// 中文句子拼接不应插入原文没有的空格；英文句子拼接必须保留空格。
func TestJoinSemanticPartsSpacing(t *testing.T) {
	if got := JoinSemanticParts("第一句。", "第二句。"); got != "第一句。第二句。" {
		t.Errorf("Chinese sentences must not be joined with a space, got %q", got)
	}
	if got := JoinSemanticParts("First one.", "Second one."); got != "First one. Second one." {
		t.Errorf("English sentences must be joined with a space, got %q", got)
	}
	if got := JoinSemanticParts("alpha,", "beta"); got != "alpha, beta" {
		t.Errorf("unexpected spacing: %q", got)
	}
	if got := JoinSemanticParts("（", "第一句。", "）"); got != "（第一句。）" {
		t.Errorf("full-width brackets must stay attached, got %q", got)
	}
}

// assertNoWordWasSplit 断言切分没有把任何单词劈成两半。
func assertNoWordWasSplit(t *testing.T, original string, chunks []string) {
	t.Helper()
	normalize := func(text string) []string {
		return strings.Fields(strings.ReplaceAll(strings.ReplaceAll(text, ",", " "), "。", " "))
	}
	want := strings.Join(normalize(original), " ")
	collected := make([]string, 0, len(chunks))
	for _, chunk := range chunks {
		collected = append(collected, normalize(chunk)...)
	}
	if got := strings.Join(collected, " "); got != want {
		t.Errorf("words were split across chunks\n got: %q\nwant: %q\nchunks: %q", got, want, chunks)
	}
}
