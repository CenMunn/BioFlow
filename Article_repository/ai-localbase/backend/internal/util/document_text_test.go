package util

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/xuri/excelize/v2"
)

func TestSemanticChunkBasic(t *testing.T) {
	text := "第一段第一句。第一段第二句。\n\n第二段第一句。"
	cfg := DefaultSemanticChunkConfig()
	cfg.MaxChunkSize = 20
	cfg.MinChunkSize = 1
	cfg.OverlapSize = 0

	chunks := SemanticChunk(text, cfg)
	if len(chunks) < 2 {
		t.Fatalf("expected multiple chunks, got %d", len(chunks))
	}
	if chunks[0] != "第一段第一句。第一段第二句。" {
		t.Fatalf("unexpected first chunk: %q", chunks[0])
	}
	if chunks[len(chunks)-1] != "第二段第一句。" {
		t.Fatalf("unexpected last chunk: %q", chunks[len(chunks)-1])
	}
}

// 重叠必须由**完整句子**构成。
// 旧实现按 rune 数从上一块尾部截断，会把半句话（"...in children with auti"）
// 拼到下一块开头；现在改为按句子取整。
func TestTrailingOverlapSentencesReturnsWholeSentences(t *testing.T) {
	text := "第一句话结束了。第二句话也结束了。第三句话继续。"

	cases := []struct {
		budget int
		want   string
	}{
		{0, ""},
		{5, ""}, // 放不下任何一个完整句子时，宁可不重叠，也不塞半句话
		{10, "第三句话继续。"},
		{19, "第二句话也结束了。第三句话继续。"},
		{200, text},
	}
	for _, tc := range cases {
		if got := trailingOverlapSentences(text, tc.budget); got != tc.want {
			t.Errorf("budget=%d: got %q, want %q", tc.budget, got, tc.want)
		}
	}
}

// 上一块只有一句时不产生重叠（否则等于把整块复制一遍，索引会翻倍）。
func TestTrailingOverlapSentencesSkipsSingleSentence(t *testing.T) {
	if got := trailingOverlapSentences("只有一句话。", 200); got != "" {
		t.Fatalf("single-sentence chunk must not be duplicated, got %q", got)
	}
}

// 端到端性质检查：分块重叠部分必须以完整句子收尾，不得出现半句话。
func TestSemanticChunkOverlapIsSentenceAligned(t *testing.T) {
	text := "第一句话结束了。第二句话也结束了。第三句话继续。第四句话收尾。"
	cfg := DefaultSemanticChunkConfig()
	cfg.MaxChunkSize = 20
	cfg.MinChunkSize = 1
	cfg.OverlapSize = 12

	chunks := SemanticChunk(text, cfg)
	if len(chunks) < 2 {
		t.Fatalf("expected multiple chunks, got %d: %q", len(chunks), chunks)
	}

	sawOverlap := false
	for i := 1; i < len(chunks); i++ {
		previous := strings.TrimSpace(chunks[i-1])
		current := strings.TrimSpace(chunks[i])
		overlap := trailingOverlapSentences(previous, cfg.OverlapSize)
		if overlap == "" {
			continue
		}
		sawOverlap = true
		if !strings.HasPrefix(current, overlap) {
			t.Errorf("chunk %d should start with the whole-sentence overlap %q, got %q", i, overlap, current)
		}
		if !IsCompleteSentenceTail(overlap) {
			t.Errorf("overlap must end with sentence punctuation, got %q", overlap)
		}
	}
	if !sawOverlap {
		t.Fatalf("expected at least one overlap, got %q", chunks)
	}
}

func TestSemanticChunkLongSentence(t *testing.T) {
	text := strings.Repeat("很长", 40) + "。"
	cfg := DefaultSemanticChunkConfig()
	cfg.MaxChunkSize = 10
	cfg.MinChunkSize = 1
	cfg.OverlapSize = 0

	chunks := SemanticChunk(text, cfg)
	if len(chunks) < 2 {
		t.Fatalf("expected forced split, got %d", len(chunks))
	}
	for i, chunk := range chunks {
		if len([]rune(chunk)) > cfg.MaxChunkSize {
			t.Fatalf("chunk %d too long: %d", i, len([]rune(chunk)))
		}
	}
}

func TestSemanticChunkMinSize(t *testing.T) {
	text := "短句。\n\n这是一个足够长的句子，用于验证最小长度过滤。"
	cfg := DefaultSemanticChunkConfig()
	cfg.MaxChunkSize = 50
	cfg.MinChunkSize = 10
	cfg.OverlapSize = 0

	chunks := SemanticChunk(text, cfg)
	if len(chunks) != 1 {
		t.Fatalf("expected short chunk to be filtered, got %d", len(chunks))
	}
	if !strings.Contains(chunks[0], "这是一个足够长的句子") {
		t.Fatalf("unexpected chunk: %q", chunks[0])
	}
}

func TestExtractDocumentTextFromCSV(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "sample.csv")
	content := "字段A,字段B,字段C\n值甲,分类一,区域甲\n值乙,分类二,区域乙\n"
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("write csv: %v", err)
	}

	text, err := ExtractDocumentText(path)
	if err != nil {
		t.Fatalf("extract csv: %v", err)
	}
	if !strings.Contains(text, "文件：sample.csv。字段：字段A、字段B、字段C。数据行数：2。") {
		t.Fatalf("expected csv summary, got %q", text)
	}
	if !strings.Contains(text, "第2行：字段A：值甲。字段B：分类一。字段C：区域甲。") {
		t.Fatalf("expected first csv row, got %q", text)
	}
}

func TestExtractDocumentTextFromXLSX(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "sample.xlsx")
	workbook := excelize.NewFile()
	defer func() { _ = workbook.Close() }()
	workbook.SetSheetName("Sheet1", "示例记录")
	if err := workbook.SetSheetRow("示例记录", "A1", &[]string{"字段A", "字段B", "字段C"}); err != nil {
		t.Fatalf("set xlsx header: %v", err)
	}
	if err := workbook.SetSheetRow("示例记录", "A2", &[]string{"值甲", "120000", "状态甲"}); err != nil {
		t.Fatalf("set xlsx row: %v", err)
	}
	if err := workbook.SaveAs(path); err != nil {
		t.Fatalf("save xlsx: %v", err)
	}

	text, err := ExtractDocumentText(path)
	if err != nil {
		t.Fatalf("extract xlsx: %v", err)
	}
	if !strings.Contains(text, "文件：sample.xlsx。工作表：示例记录。字段：字段A、字段B、字段C。数据行数：1。") {
		t.Fatalf("expected xlsx summary, got %q", text)
	}
	if !strings.Contains(text, "第2行：工作表：示例记录；字段A：值甲。字段B：120000。字段C：状态甲。") {
		t.Fatalf("expected xlsx row, got %q", text)
	}
}

func TestExtractStructuredTableSummaryFromCSV(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "sample-users.csv")
	content := "类别,数量,状态\n甲类,120,启用\n乙类,80,启用\n甲类,100,停用\n丙类,60,启用\n"
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("write csv: %v", err)
	}

	text, err := ExtractDocumentText(path)
	if err != nil {
		t.Fatalf("extract csv: %v", err)
	}
	if !strings.Contains(text, "统计摘要：文件《sample-users.csv》共有4条数据记录。") {
		t.Fatalf("expected table-level summary, got %q", text)
	}
	if !strings.Contains(text, "统计摘要：字段“类别”为类别列，共4个非空值，主要分布为：甲类(2)、") {
		t.Fatalf("expected category summary prefix, got %q", text)
	}
	if !strings.Contains(text, "乙类(1)") || !strings.Contains(text, "丙类(1)") {
		t.Fatalf("expected category summary entries, got %q", text)
	}
	if !strings.Contains(text, "统计摘要：字段“数量”为数值列，非空值4个，最小值60.00，最大值120.00，平均值90.00。") {
		t.Fatalf("expected numeric summary, got %q", text)
	}
}

func TestExtractStructuredTablesFromCSV(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "users.csv")
	content := "姓名,城市,薪资\n张三,上海,24000\n李四,北京,18000\n"
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("write csv: %v", err)
	}

	tables, err := ExtractStructuredTables(path)
	if err != nil {
		t.Fatalf("extract structured tables: %v", err)
	}
	if len(tables) != 1 {
		t.Fatalf("expected one table, got %d", len(tables))
	}
	if strings.Join(tables[0].Headers, ",") != "姓名,城市,薪资" {
		t.Fatalf("unexpected headers: %#v", tables[0].Headers)
	}
	if len(tables[0].Rows) != 2 {
		t.Fatalf("expected two rows, got %d", len(tables[0].Rows))
	}
	if tables[0].Rows[0].Number != 2 || tables[0].Rows[0].Values[0] != "张三" {
		t.Fatalf("unexpected first row: %#v", tables[0].Rows[0])
	}
}
