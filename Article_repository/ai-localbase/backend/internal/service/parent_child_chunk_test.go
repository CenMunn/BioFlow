package service

import (
	"strings"
	"testing"

	"ai-localbase/internal/model"
	"ai-localbase/internal/util"
)

func TestDefaultParentChildChunkConfig(t *testing.T) {
	cfg := DefaultParentChildChunkConfig(1200, 450)

	if cfg.ParentTargetSize != 1200 {
		t.Errorf("ParentTargetSize = %d, want 1200", cfg.ParentTargetSize)
	}
	if cfg.ParentMaxSize <= cfg.ParentTargetSize {
		t.Errorf("ParentMaxSize (%d) must exceed ParentTargetSize (%d)", cfg.ParentMaxSize, cfg.ParentTargetSize)
	}
	// 子文档长度上限沿用原有的 maxChunkSize 语义
	if cfg.Child.TargetSize != 450 {
		t.Errorf("child TargetSize = %d, want 450", cfg.Child.TargetSize)
	}
	if cfg.Child.MaxSize <= cfg.Child.TargetSize {
		t.Errorf("child MaxSize (%d) must exceed child TargetSize (%d)", cfg.Child.MaxSize, cfg.Child.TargetSize)
	}

	fallback := DefaultParentChildChunkConfig(0, 0)
	if fallback.ParentTargetSize != defaultParentTargetSize {
		t.Errorf("expected default parent target %d, got %d", defaultParentTargetSize, fallback.ParentTargetSize)
	}
	if fallback.Child.TargetSize != defaultChunkSize {
		t.Errorf("expected default child target %d, got %d", defaultChunkSize, fallback.Child.TargetSize)
	}
}

// 父文档按段落聚合：达到目标长度后收束，多余的段落进入下一个父文档。
func TestGroupParagraphsIntoParentsRespectsTarget(t *testing.T) {
	paragraphs := [][]string{
		{strings.Repeat("a", 100)},
		{strings.Repeat("b", 100)},
		{strings.Repeat("c", 100)},
	}

	groups := groupParagraphsIntoParents(paragraphs, 150, 400)

	if len(groups) != 2 {
		t.Fatalf("expected 2 parent groups, got %d", len(groups))
	}
	if len(groups[0]) != 2 {
		t.Errorf("first parent should hold 2 paragraphs, got %d", len(groups[0]))
	}
	if len(groups[1]) != 1 {
		t.Errorf("second parent should hold 1 paragraph, got %d", len(groups[1]))
	}
}

// 单个段落超过硬上限时也必须切开，不能让父文档无限增长。
// target=150 而 max=400 时，每个 300 字符的段落都应独占一个父文档。
func TestGroupParagraphsIntoParentsRespectsMax(t *testing.T) {
	paragraphs := [][]string{
		{strings.Repeat("a", 300)},
		{strings.Repeat("b", 300)},
		{strings.Repeat("c", 300)},
	}

	groups := groupParagraphsIntoParents(paragraphs, 150, 400)

	if len(groups) != 3 {
		t.Fatalf("expected 3 parent groups (300+300 would exceed max 400), got %d", len(groups))
	}
	for i, group := range groups {
		if len(group) != 1 {
			t.Errorf("group %d should hold 1 paragraph, got %d", i, len(group))
		}
	}
}

// max 小于 target 时应自动抬升为 target，保证配置不会互相矛盾。
func TestGroupParagraphsIntoParentsRaisesMaxToTarget(t *testing.T) {
	paragraphs := [][]string{
		{strings.Repeat("a", 300)},
		{strings.Repeat("b", 300)},
		{strings.Repeat("c", 300)},
	}

	groups := groupParagraphsIntoParents(paragraphs, 1000, 400)

	if len(groups) != 1 {
		t.Fatalf("max should be raised to target, expected a single group, got %d", len(groups))
	}
	if len(groups[0]) != 3 {
		t.Errorf("expected 3 paragraphs aggregated, got %d", len(groups[0]))
	}
}

func TestGroupParagraphsIntoParentsSkipsEmpty(t *testing.T) {
	groups := groupParagraphsIntoParents([][]string{{}, {"  "}, {strings.Repeat("x", 10)}}, 100, 200)
	if len(groups) != 1 {
		t.Fatalf("expected 1 group, got %d", len(groups))
	}
	if len(groups[0]) != 1 {
		t.Fatalf("expected 1 paragraph in group, got %d", len(groups[0]))
	}
}

// 子文档切分必须遵守 MaxSize（即原 maxChunkSize）。
// 整篇没有空行分段时，父文档不能退化成「整篇一个块」，必须按句子边界再切。
func TestSplitOversizeParentBlocksSplitsSingleParagraph(t *testing.T) {
	// 一个段落、20 个句子，每句 30 字符 => 总长约 620
	sentences := make([]string, 0, 20)
	for i := 0; i < 20; i++ {
		sentences = append(sentences, strings.Repeat("s", 30))
	}
	blocks := [][][]string{{sentences}}

	got := splitOversizeParentBlocks(blocks, 200)

	if len(got) < 3 {
		t.Fatalf("expected the single oversize paragraph to be split into >=3 parents, got %d", len(got))
	}
	for i, block := range got {
		total := 0
		for _, group := range block {
			total += paragraphRuneLength(group)
		}
		if total > 200 {
			t.Errorf("parent %d exceeds max 200: %d", i, total)
		}
	}
}

// 单个句子就超过上限时先按窗口硬切，保证父文档长度严格有界。
func TestSplitOversizeParentBlocksHardSplitsHugeSentence(t *testing.T) {
	blocks := [][][]string{{{strings.Repeat("x", 900)}}}

	got := splitOversizeParentBlocks(blocks, 200)

	if len(got) < 4 {
		t.Fatalf("expected the huge sentence to be window-split, got %d parents", len(got))
	}
	for i, block := range got {
		total := 0
		for _, group := range block {
			total += paragraphRuneLength(group)
		}
		if total > 200 {
			t.Errorf("parent %d exceeds max 200: %d", i, total)
		}
	}
}

// 未超限的父文档应原样保留，避免无谓地打散原有段落结构。
func TestSplitOversizeParentBlocksKeepsSmallBlocks(t *testing.T) {
	blocks := [][][]string{
		{{strings.Repeat("a", 50)}, {strings.Repeat("b", 50)}},
	}

	got := splitOversizeParentBlocks(blocks, 400)

	if len(got) != 1 {
		t.Fatalf("small block should be preserved, got %d blocks", len(got))
	}
	if len(got[0]) != 2 {
		t.Errorf("expected 2 paragraphs preserved, got %d", len(got[0]))
	}
}

func TestBuildChildTextsRespectsChildMaxSize(t *testing.T) {
	cfg := SemanticChunkByEmbeddingConfig{TargetSize: 60, MaxSize: 75, MinSize: 30, SimilarityThreshold: 0.72}
	units := []semanticSentenceUnit{
		{text: strings.Repeat("a", 40), para: 0, length: 40, vector: []float64{1, 0}},
		{text: strings.Repeat("b", 40), para: 1, length: 40, vector: []float64{0, 1}},
		{text: strings.Repeat("c", 40), para: 1, length: 40, vector: []float64{0, 1}},
	}

	got := buildChildTexts(units, cfg, defaultChildOverlapSentences)

	if len(got) != 3 {
		t.Fatalf("expected 3 children (each 40 chars, max 75), got %d: %q", len(got), got)
	}
	for _, child := range got {
		if n := runeLen(child); n > cfg.MaxSize {
			t.Errorf("child exceeds MaxSize: %d > %d (%q)", n, cfg.MaxSize, child)
		}
	}
}

// 过短的子文档应按语义相似度并回相邻子文档。
func TestBuildChildTextsMergesShortChild(t *testing.T) {
	cfg := SemanticChunkByEmbeddingConfig{TargetSize: 20, MaxSize: 30, MinSize: 10, SimilarityThreshold: 0.72}
	units := []semanticSentenceUnit{
		{text: strings.Repeat("a", 20), para: 0, length: 20, vector: []float64{1, 0}},
		{text: strings.Repeat("b", 5), para: 0, length: 5, vector: []float64{0, 1}},
	}

	got := buildChildTexts(units, cfg, defaultChildOverlapSentences)

	if len(got) != 1 {
		t.Fatalf("expected the 5-char child to be merged into its neighbour, got %d: %q", len(got), got)
	}
	if !strings.Contains(got[0], "aaaa") || !strings.Contains(got[0], "bbbbb") {
		t.Errorf("merged child should contain both sentences: %q", got[0])
	}
}

// 单句本身超过上限时按窗口兜底切分。
func TestBuildChildTextsSplitsOversizeSingleUnit(t *testing.T) {
	cfg := SemanticChunkByEmbeddingConfig{TargetSize: 20, MaxSize: 25, MinSize: 10, SimilarityThreshold: 0.72}
	units := []semanticSentenceUnit{
		{text: strings.Repeat("z", 60), para: 0, length: 60, vector: []float64{1, 0}},
	}

	got := buildChildTexts(units, cfg, defaultChildOverlapSentences)

	if len(got) != 3 {
		t.Fatalf("expected 60 chars split into 3 windows of 25, got %d: %q", len(got), got)
	}
	for _, child := range got {
		if n := runeLen(child); n > cfg.MaxSize {
			t.Errorf("oversize window: %d > %d", n, cfg.MaxSize)
		}
	}
}

// 同一父文档下的多个子文档应折叠为一个条目，正文替换为父文档全文，分数取最高。
func TestExpandRetrievedChunksToParentsGroupsChildren(t *testing.T) {
	chunks := []RetrievedChunk{
		{DocumentChunk: DocumentChunk{
			ID: "c1", DocumentID: "d1", Index: 0, Text: "child one",
			ParentID: "p1", ParentIndex: 0, ParentText: "PARENT ONE",
		}, Score: 0.5},
		{DocumentChunk: DocumentChunk{
			ID: "c2", DocumentID: "d1", Index: 1, Text: "child two",
			ParentID: "p1", ParentIndex: 0, ParentText: "PARENT ONE",
		}, Score: 0.9},
		{DocumentChunk: DocumentChunk{
			ID: "c3", DocumentID: "d1", Index: 2, Text: "child three",
			ParentID: "p2", ParentIndex: 1, ParentText: "PARENT TWO",
		}, Score: 0.7},
		// 结构化摘要没有父文档，应原样保留
		{DocumentChunk: DocumentChunk{ID: "s1", DocumentID: "d1", Index: 3, Text: "统计摘要：共 3 行"}, Score: 0.6},
	}

	got := expandRetrievedChunksToParents(chunks)

	if len(got) != 3 {
		t.Fatalf("expected 3 expanded chunks, got %d", len(got))
	}
	if got[0].ID != "p1" || got[0].Text != "PARENT ONE" {
		t.Errorf("top chunk should be parent p1, got id=%q text=%q", got[0].ID, got[0].Text)
	}
	if got[0].Score != 0.9 {
		t.Errorf("expanded parent should keep the best child score 0.9, got %v", got[0].Score)
	}
	if got[0].ChildID != "c2" {
		t.Errorf("expanded parent should record the winning child id, got %q", got[0].ChildID)
	}
	if got[0].ParentIndex != 0 {
		t.Errorf("expanded parent should carry parent index 0, got %d", got[0].ParentIndex)
	}
	if got[1].ID != "p2" || got[1].Text != "PARENT TWO" {
		t.Errorf("second chunk should be parent p2, got id=%q text=%q", got[1].ID, got[1].Text)
	}
	if got[2].ID != "s1" {
		t.Errorf("standalone chunk should be preserved, got %q", got[2].ID)
	}
}

// 没有父子信息的检索结果（旧索引）必须保持原样，保证向后兼容。
func TestExpandRetrievedChunksToParentsBackwardCompatible(t *testing.T) {
	chunks := []RetrievedChunk{
		{DocumentChunk: DocumentChunk{ID: "c1", DocumentID: "d1", Index: 0, Text: "one"}, Score: 0.4},
		{DocumentChunk: DocumentChunk{ID: "c2", DocumentID: "d1", Index: 1, Text: "two"}, Score: 0.8},
	}

	got := expandRetrievedChunksToParents(chunks)

	if len(got) != 2 {
		t.Fatalf("expected 2 chunks untouched, got %d", len(got))
	}
	if got[0].ID != "c2" || got[1].ID != "c1" {
		t.Errorf("chunks should stay sorted by score, got %q then %q", got[0].ID, got[1].ID)
	}
}

func TestExpandRetrievedChunksToParentsEmpty(t *testing.T) {
	if got := expandRetrievedChunksToParents(nil); got != nil {
		t.Fatalf("expected nil for empty input, got %v", got)
	}
}

func TestDeriveDocumentTopic(t *testing.T) {
	// DOI 形式的文件名没有语义，应改用正文首行
	doi := deriveDocumentTopic("10.1016_j.phrs.2026.108284.txt",
		"Gut microbiota dysbiosis in children with autism spectrum disorder\n\nAbstract ...")
	if !strings.HasPrefix(doi, "Gut microbiota dysbiosis") {
		t.Errorf("expected first body line as topic, got %q", doi)
	}

	// 有语义的文件名优先
	named := deriveDocumentTopic("autism_gut_microbiome_review.txt", "body text here")
	if !strings.Contains(named, "autism gut microbiome") {
		t.Errorf("expected file name derived topic, got %q", named)
	}

	if got := deriveDocumentTopic("x.txt", "short"); got != "" {
		t.Errorf("expected empty topic when nothing usable, got %q", got)
	}
}

func TestPrepareDocumentTextCleansAndResolves(t *testing.T) {
	svc := NewRagService()
	raw := strings.Join([]string{
		"<p>Autism spectrum disorder (ASD) is associated with gut microbiota dysbiosis.</p>",
		"Downloaded from https://example.org",
		"It affects social behaviour.",
	}, "\n")

	prepared := svc.PrepareDocumentText("asd_microbiome_review.txt", raw)

	if strings.Contains(prepared.Text, "<p>") || strings.Contains(prepared.Text, "Downloaded from") {
		t.Errorf("preprocessing should strip noise:\n%s", prepared.Text)
	}
	if prepared.Clean.HTMLTagsRemoved == 0 {
		t.Errorf("expected html tag removal counted")
	}
	if prepared.Clean.BoilerplateLines == 0 {
		t.Errorf("expected boilerplate line counted")
	}
	if prepared.Topic == "" {
		t.Errorf("expected a derived document topic")
	}
	if prepared.Anaphora.Replacements == 0 {
		t.Errorf("expected the sentence-initial 'It' to be resolved:\n%s", prepared.Text)
	}
	if !strings.Contains(prepared.Text, "ASD affects social behaviour") {
		t.Errorf("expected pronoun resolution using the acronym entity:\n%s", prepared.Text)
	}
}

func TestPrepareDocumentTextEmpty(t *testing.T) {
	svc := NewRagService()
	prepared := svc.PrepareDocumentText("empty.txt", "   ")
	if prepared.Text != "   " {
		t.Errorf("empty input should be returned as-is, got %q", prepared.Text)
	}
}

// 结构化摘要块必须仍然前置且可被识别，避免预处理破坏表格类文档的问答路径。
func TestBuildStructuredSummaryChunksStillPrepended(t *testing.T) {
	document := model.Document{ID: "doc-1", KnowledgeBaseID: "kb-1", Name: "employees.csv"}
	text := "统计摘要：共 2 行\n第1行：a,b\n第2行：c,d"

	summary := buildStructuredSummaryChunks(document, text, 10)
	if len(summary) == 0 {
		t.Fatalf("expected structured summary chunks to be extracted")
	}
	if summary[0].Kind != "structured_summary" {
		t.Errorf("expected kind structured_summary, got %q", summary[0].Kind)
	}
	if summary[0].Index != 10 {
		t.Errorf("expected start index 10, got %d", summary[0].Index)
	}
}

// 相邻子文档的重叠必须由**完整句子**构成。
func TestApplySentenceOverlapPrependsWholeSentence(t *testing.T) {
	units := []semanticSentenceUnit{
		{text: "Alpha one.", para: 0, length: 10, vector: []float64{1, 0}},
		{text: "Alpha two.", para: 0, length: 10, vector: []float64{1, 0}},
		{text: "Beta one.", para: 0, length: 9, vector: []float64{0, 1}},
	}
	groups := [][]int{{0, 1}, {2}}
	cfg := SemanticChunkByEmbeddingConfig{TargetSize: 40, MaxSize: 60, MinSize: 5, SimilarityThreshold: 0.72}

	got := applySentenceOverlap(groups, units, cfg, 1)

	if len(got) != 2 {
		t.Fatalf("expected 2 groups, got %v", got)
	}
	if len(got[1]) != 2 || got[1][0] != 1 || got[1][1] != 2 {
		t.Fatalf("second group should begin with the last sentence of the first group, got %v", got[1])
	}
	// 不得修改入参（否则会级联污染后续计算）
	if len(groups[1]) != 1 {
		t.Errorf("input groups must not be mutated, got %v", groups[1])
	}
}

// 加上重叠会超过上限时，应放弃重叠，而不是把子文档撑爆。
func TestApplySentenceOverlapSkipsWhenExceedingMaxSize(t *testing.T) {
	units := []semanticSentenceUnit{
		{text: strings.Repeat("a", 40), para: 0, length: 40, vector: []float64{1, 0}},
		{text: strings.Repeat("b", 40), para: 0, length: 40, vector: []float64{0, 1}},
	}
	groups := [][]int{{0}, {1}}
	cfg := SemanticChunkByEmbeddingConfig{TargetSize: 40, MaxSize: 50, MinSize: 5, SimilarityThreshold: 0.72}

	got := applySentenceOverlap(groups, units, cfg, 1)

	if len(got[1]) != 1 {
		t.Fatalf("overlap must be skipped when it would exceed MaxSize, got %v", got[1])
	}
}

// 端到端：子文档重叠后仍受长度上限约束，且每个子文档都终结于句子边界。
func TestBuildChildTextsOverlapIsSentenceAligned(t *testing.T) {
	cfg := SemanticChunkByEmbeddingConfig{TargetSize: 60, MaxSize: 100, MinSize: 20, SimilarityThreshold: 0.1}
	units := []semanticSentenceUnit{
		{text: "Alpha sentence one.", para: 0, length: 19, vector: []float64{1, 0}},
		{text: "Alpha sentence two.", para: 0, length: 19, vector: []float64{1, 0}},
		{text: "Alpha sentence three.", para: 0, length: 21, vector: []float64{1, 0}},
		{text: "Alpha sentence four.", para: 0, length: 20, vector: []float64{0, 1}},
	}

	got := buildChildTexts(units, cfg, 1)

	if len(got) < 2 {
		t.Fatalf("expected multiple children, got %q", got)
	}
	for i, child := range got {
		if n := runeLen(child); n > cfg.MaxSize {
			t.Errorf("child %d exceeds MaxSize: %d > %d (%q)", i, n, cfg.MaxSize, child)
		}
		if !util.IsCompleteSentenceTail(child) {
			t.Errorf("child %d does not end at a sentence boundary: %q", i, child)
		}
	}
	// 第二块应当以**上一块的最后一个完整句子**开头（重叠内容为完整句子）
	previous := strings.TrimSpace(got[0])
	lastSentence := ""
	if idx := strings.LastIndex(previous, ". "); idx >= 0 {
		lastSentence = previous[idx+2:]
	}
	if lastSentence == "" {
		t.Fatalf("could not derive the last sentence of the first child: %q", previous)
	}
	if !strings.HasPrefix(got[1], lastSentence) {
		t.Errorf("second child should start with the overlap sentence %q, got %q", lastSentence, got[1])
	}
	if !util.IsCompleteSentenceTail(lastSentence) {
		t.Errorf("overlap must be a complete sentence, got %q", lastSentence)
	}
}

// 重叠内容不得超出上限，且不得出现半句话。
func TestBuildChildTextsOverlapNeverExceedsChildMaxSize(t *testing.T) {
	cfg := SemanticChunkByEmbeddingConfig{TargetSize: 50, MaxSize: 60, MinSize: 20, SimilarityThreshold: 0.1}
	units := make([]semanticSentenceUnit, 0, 12)
	for i := 0; i < 12; i++ {
		units = append(units, semanticSentenceUnit{
			text:   "Sentence number " + string(rune('A'+i)) + " goes here.",
			para:   0,
			length: 28,
			vector: []float64{1, 0},
		})
	}

	got := buildChildTexts(units, cfg, 1)

	for i, child := range got {
		if n := runeLen(child); n > cfg.MaxSize {
			t.Errorf("child %d exceeds MaxSize: %d > %d (%q)", i, n, cfg.MaxSize, child)
		}
	}
}

func runeLen(text string) int {
	return len([]rune(text))
}
