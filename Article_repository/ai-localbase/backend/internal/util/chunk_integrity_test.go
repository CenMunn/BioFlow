package util

import (
	"strings"
	"testing"
)

func TestEndsWithSentenceTerminator(t *testing.T) {
	complete := []string{
		"这是一句完整的话。",
		"An English sentence ends here.",
		`He said "it works."`,   // 句末标点后跟闭合引号
		"列举如下：",              // 冒号可作为收尾
		"First clause; second clause;",
	}
	for _, text := range complete {
		if !endsWithSentenceTerminator(text) {
			t.Errorf("expected complete tail: %q", text)
		}
	}

	incomplete := []string{
		"这句话被切断了，没有结束标点",
		"This sentence was cut off mid",
		"",
	}
	for _, text := range incomplete {
		if endsWithSentenceTerminator(text) {
			t.Errorf("expected incomplete tail: %q", text)
		}
	}
}

// 前一块没有以句末标点收尾 -> 边界切在了句子中间，两侧都要报出来。
func TestCheckChunkIntegrityDetectsMidSentenceBoundary(t *testing.T) {
	chunks := []string{
		"This paragraph was deliberately made long enough to be judged as prose and then it got cut off",
		"right in the middle of a sentence here.",
	}

	issues := CheckChunkIntegrity(chunks)

	kinds := issueKinds(issues)
	if kinds[IssueEndsMidSentence] != 1 {
		t.Errorf("expected 1 ends_mid_sentence, got %v", issues)
	}
	if kinds[IssueStartsMidSentence] != 1 {
		t.Errorf("expected 1 starts_mid_sentence, got %v", issues)
	}
}

// 短行（标题、编号、表头）不带句末标点是正常的，不能误报。
func TestCheckChunkIntegrityIgnoresShortLines(t *testing.T) {
	chunks := []string{"Introduction", "Methods and Materials", "Results"}

	if issues := CheckChunkIntegrity(chunks); len(issues) != 0 {
		t.Fatalf("short headings must not be flagged, got %v", issues)
	}
}

// 结构化表格块自带完整结构，不参与句子边界判定。
func TestCheckChunkIntegrityIgnoresStructuredChunks(t *testing.T) {
	chunks := []string{"统计摘要：共 3 行", "第1行：a,b,c"}

	if issues := CheckChunkIntegrity(chunks); len(issues) != 0 {
		t.Fatalf("structured chunks must not be flagged, got %v", issues)
	}
}

func TestCheckChunkIntegrityDetectsUnbalancedBrackets(t *testing.T) {
	issues := CheckChunkIntegrity([]string{"括号不配对的内容（缺少右括号。"})

	if !hasIssueKind(issues, IssueUnbalancedBrackets) {
		t.Fatalf("expected unbalanced_brackets, got %v", issues)
	}
}

func TestCheckChunkIntegrityDetectsUnbalancedQuotes(t *testing.T) {
	// 注意：只用**一个**双引号（奇数），构造真正的不配对情况
	issues := CheckChunkIntegrity([]string{`引号数量是奇数的内容 "这里。`})

	if !hasIssueKind(issues, IssueUnbalancedQuotes) {
		t.Fatalf("expected unbalanced_quotes, got %v", issues)
	}
}

func TestCheckChunkIntegrityDetectsDanglingConnector(t *testing.T) {
	chunks := []string{
		"The first paragraph is long enough to count as prose body text here.",
		"and this continues the previous thought across the boundary.",
	}

	issues := CheckChunkIntegrity(chunks)

	if !hasIssueKind(issues, IssueDanglingConnector) {
		t.Fatalf("expected dangling_connector, got %v", issues)
	}
}

// 被强行切开的边界应被合并回去。
func TestRepairChunkIntegrityMergesFragment(t *testing.T) {
	chunks := []string{
		"This paragraph was deliberately made long enough to be judged as prose and then it got cut off",
		"right in the middle of a sentence here.",
	}

	repaired, remaining := RepairChunkIntegrity(chunks, 2000)

	if len(repaired) != 1 {
		t.Fatalf("expected the fragment to be merged back, got %d: %q", len(repaired), repaired)
	}
	if !endsWithSentenceTerminator(repaired[0]) {
		t.Errorf("merged chunk should end at a sentence boundary: %q", repaired[0])
	}
	if hasIssueKind(remaining, IssueEndsMidSentence) {
		t.Errorf("boundary issue should be resolved, got %v", remaining)
	}
}

// 已经完整的块不应被动到。
func TestRepairChunkIntegrityKeepsCleanChunks(t *testing.T) {
	chunks := []string{
		"The first paragraph is a complete sentence and stays as is.",
		"The second paragraph is also a complete sentence.",
		"The third paragraph ends properly too.",
	}

	repaired, remaining := RepairChunkIntegrity(chunks, 2000)

	if len(repaired) != len(chunks) {
		t.Fatalf("clean chunks must not be merged, got %d: %q", len(repaired), repaired)
	}
	if len(remaining) != 0 {
		t.Fatalf("expected no remaining issues, got %v", remaining)
	}
}

// 合并会超过上限时不做合并，并把问题如实报出。
func TestRepairChunkIntegrityRespectsMaxSize(t *testing.T) {
	chunks := []string{
		"abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyz",
		"abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyz",
	}

	repaired, remaining := RepairChunkIntegrity(chunks, 60)

	if len(repaired) != 2 {
		t.Fatalf("merge would exceed maxSize, chunks should stay separate, got %q", repaired)
	}
	if !hasIssueKind(remaining, IssueEndsMidSentence) {
		t.Errorf("unresolved boundary should be reported, got %v", remaining)
	}
}

func TestRepairChunkIntegritySingleChunk(t *testing.T) {
	repaired, issues := RepairChunkIntegrity([]string{"只有一块。"}, 100)
	if len(repaired) != 1 || len(issues) != 0 {
		t.Fatalf("unexpected result: %q %v", repaired, issues)
	}
}

func TestTrailingSentences(t *testing.T) {
	text := "第一句。第二句。第三句。"

	if got := TrailingSentences(text, 1); got != "第三句。" {
		t.Errorf("TrailingSentences(1) = %q, want %q", got, "第三句。")
	}
	if got := TrailingSentences(text, 2); got != "第二句。第三句。" {
		t.Errorf("TrailingSentences(2) = %q", got)
	}
	// 句数不足时返回整个文本
	if got := TrailingSentences(text, 3); got != text {
		t.Errorf("TrailingSentences(3) = %q, want the whole text", got)
	}
	if got := TrailingSentences(text, 9); got != text {
		t.Errorf("TrailingSentences(9) = %q, want the whole text", got)
	}
	if got := TrailingSentences(text, 0); got != "" {
		t.Errorf("TrailingSentences(0) should be empty, got %q", got)
	}
}

func TestSummarizeIntegrityIssues(t *testing.T) {
	issues := []ChunkIntegrityIssue{
		{Kind: IssueEndsMidSentence},
		{Kind: IssueEndsMidSentence},
		{Kind: IssueUnbalancedQuotes},
	}
	summary := SummarizeIntegrityIssues(issues)
	if summary[IssueEndsMidSentence] != 2 || summary[IssueUnbalancedQuotes] != 1 {
		t.Fatalf("unexpected summary: %v", summary)
	}
}

func TestDescribeIntegrityIssue(t *testing.T) {
	got := DescribeIntegrityIssue(ChunkIntegrityIssue{Index: 3, Kind: IssueUnbalancedQuotes, Detail: "中文双引号不配对"})
	if !strings.Contains(got, "chunk#3") || !strings.Contains(got, IssueUnbalancedQuotes) {
		t.Fatalf("unexpected description: %q", got)
	}
}

func issueKinds(issues []ChunkIntegrityIssue) map[string]int {
	return SummarizeIntegrityIssues(issues)
}

func hasIssueKind(issues []ChunkIntegrityIssue, kind string) bool {
	for _, issue := range issues {
		if issue.Kind == kind {
			return true
		}
	}
	return false
}
