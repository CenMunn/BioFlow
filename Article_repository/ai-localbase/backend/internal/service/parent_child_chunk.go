package service

import (
	"context"
	"fmt"
	"log"
	"regexp"
	"sort"
	"strings"

	"ai-localbase/internal/model"
	"ai-localbase/internal/util"
)

const (
	// defaultParentTargetSize 父文档目标长度（rune）。
	// 父文档是最终交给大模型的上下文单元，因此取值大于子文档但不宜过大，
	// 以免挤占 RETRIEVAL_MAX_CONTEXT_CHARS 预算。
	defaultParentTargetSize = 1200
	// defaultParentMaxSize 父文档硬上限。
	defaultParentMaxSize = 1800
)

// ParentChildChunkConfig 父子文档（ParentDocumentRetriever）分块配置。
//
// 分块顺序与用户预期一致：
//  1. 按段落划分，聚合成「父文档」（ParentTargetSize 为聚合目标）；
//  2. 在父文档内部按语义相关性切分为「子文档」（Child 控制子文档长度上限）。
//
// 向量化入库时只对子文档建立索引；父文档正文随子文档一同落入 payload，
// 检索命中子文档后再把父文档交给大模型。
type ParentChildChunkConfig struct {
	ParentTargetSize int
	ParentMaxSize    int
	Child            SemanticChunkByEmbeddingConfig
	// ChildOverlapSentences 相邻子文档之间按**完整句子**重叠的句子数。
	// 重叠内容永远是完整句子（不会出现半句话），且在加上后会超过子文档
	// 长度上限时自动减少重叠句数。<=0 时取默认值 defaultChildOverlapSentences。
	ChildOverlapSentences int
}

// defaultChildOverlapSentences 默认重叠 1 个完整句子。
const defaultChildOverlapSentences = 1

// DefaultParentChildChunkConfig 推导默认父子分块参数。
// childTarget 即原有的分块长度上限（默认 450）。
func DefaultParentChildChunkConfig(parentTarget, childTarget int) ParentChildChunkConfig {
	if parentTarget <= 0 {
		parentTarget = defaultParentTargetSize
	}
	if childTarget <= 0 {
		childTarget = defaultChunkSize
	}
	parentMax := parentTarget + parentTarget/2
	if parentMax < defaultParentMaxSize && parentMax < parentTarget+200 {
		parentMax = parentTarget + 200
	}
	return ParentChildChunkConfig{
		ParentTargetSize:      parentTarget,
		ParentMaxSize:         parentMax,
		Child:                 DefaultSemanticChunkByEmbeddingConfig(childTarget),
		ChildOverlapSentences: defaultChildOverlapSentences,
	}
}

// PreparedDocumentText 预处理结果：清洗 + 指代消解。
type PreparedDocumentText struct {
	Text     string
	Topic    string
	Clean    util.CleanStats
	Anaphora util.AnaphoraResult
}

var doiLikeNamePattern = regexp.MustCompile(`^10\.\d{4,9}[_/]`)

// PrepareDocumentText 对抽取出的正文做质量优化：
//
//  1. 噪声清理（HTML 标签/实体、控制字符、Unicode 归一化、模板化页眉页脚、尾部参考文献）；
//  2. 指代消解：把句首代词替换为明确实体名，弥补分块造成的上下文断裂。
//
// 停用词不在此处删除（见 util.CleanDocumentText 说明）。
func (s *RagService) PrepareDocumentText(documentName, text string) PreparedDocumentText {
	result := PreparedDocumentText{Text: text}
	if strings.TrimSpace(text) == "" {
		return result
	}

	cleaned, stats := util.CleanDocumentText(text)
	result.Clean = stats
	if strings.TrimSpace(cleaned) == "" {
		return result
	}

	topic := deriveDocumentTopic(documentName, cleaned)
	result.Topic = topic

	anaphora := util.ResolveAnaphora(cleaned, topic)
	result.Anaphora = anaphora
	result.Text = anaphora.Text

	log.Printf(
		"preprocess document %q: runes %d->%d, html_tags=%d, entities=%d, control=%d, unicode=%d, boilerplate_lines=%d, references_trimmed=%t, anaphora=%d, topic=%q",
		documentName,
		stats.OriginalRunes,
		stats.CleanedRunes,
		stats.HTMLTagsRemoved,
		stats.HTMLEntitiesFixed,
		stats.ControlRunesDrop,
		stats.UnicodeNormalized,
		stats.BoilerplateLines,
		stats.ReferencesTrimmed,
		anaphora.Replacements,
		truncateRunes(topic, 80),
	)
	return result
}

// deriveDocumentTopic 推导文档主题实体，作为指代消解的兜底先行词。
// 文件名形如 DOI（10.1016_j.phrs.2026.108284.txt）时改用正文首行（通常是论文标题）。
func deriveDocumentTopic(documentName, cleanedText string) string {
	name := strings.TrimSpace(documentName)
	name = strings.TrimSuffix(name, ".txt")
	name = strings.TrimSuffix(name, ".pdf")
	name = strings.TrimSuffix(name, ".md")

	if name != "" && !doiLikeNamePattern.MatchString(name) && !strings.HasPrefix(name, "10.") {
		candidate := strings.Join(strings.Fields(strings.ReplaceAll(strings.ReplaceAll(name, "_", " "), "-", " ")), " ")
		if runeCountOf(candidate) >= 6 {
			return candidate
		}
	}

	for _, line := range strings.Split(cleanedText, "\n") {
		trimmed := strings.TrimSpace(line)
		if runeCountOf(trimmed) < 12 {
			continue
		}
		// 跳过明显的结构化/表格行
		if strings.HasPrefix(trimmed, "统计摘要：") || strings.Contains(trimmed, "行：") {
			continue
		}
		return truncateRunes(trimmed, 160)
	}
	return ""
}

func runeCountOf(text string) int {
	return util.RuneCount(text)
}

// BuildDocumentChunksParentChild 构建「父文档 + 子文档」两级分块。
//
// 流程：
//  1. 段落→父文档：按段落聚合，直到达到 ParentTargetSize 或超过 ParentMaxSize；
//  2. 一次性嵌入全部句子（单次批量，避免逐父文档多次调用）；
//  3. 父文档内部按语义相似度切子文档（长度上限由 cfg.Child.MaxSize 控制，
//     即原有的 maxChunkSize 语义）。
func (s *RagService) BuildDocumentChunksParentChild(
	ctx context.Context,
	document model.Document,
	text string,
	embeddingCfg model.EmbeddingModelConfig,
	vectorSize int,
	cfg ParentChildChunkConfig,
) ([]DocumentChunk, error) {
	if cfg.ParentTargetSize <= 0 || cfg.Child.MaxSize <= 0 {
		cfg = DefaultParentChildChunkConfig(cfg.ParentTargetSize, cfg.Child.MaxSize)
	}

	paragraphSentences := util.SplitTextIntoParagraphSentences(text)
	if len(paragraphSentences) == 0 {
		return nil, nil
	}

	// 1) 段落 -> 父文档
	parentParagraphs := groupParagraphsIntoParents(paragraphSentences, cfg.ParentTargetSize, cfg.ParentMaxSize)
	// 提取出的正文常常整篇没有空行（被归一为单个段落），仅靠段落边界无法保证
	// 父文档长度有界，这里再按句子边界切一次。
	parentParagraphs = splitOversizeParentBlocks(parentParagraphs, cfg.ParentMaxSize)
	if len(parentParagraphs) == 0 {
		return nil, nil
	}

	// 2) 展开为句子单元（para 使用父文档内的局部段落序号），并记录每个父文档的区间
	type parentSpan struct{ start, end int }
	units := make([]semanticSentenceUnit, 0, len(paragraphSentences)*4)
	spans := make([]parentSpan, 0, len(parentParagraphs))
	for _, paragraphs := range parentParagraphs {
		start := len(units)
		for localPara, sentences := range paragraphs {
			for _, sentence := range sentences {
				trimmed := strings.TrimSpace(sentence)
				if trimmed == "" {
					continue
				}
				units = append(units, semanticSentenceUnit{
					text:   trimmed,
					para:   localPara,
					length: util.RuneCount(trimmed),
				})
			}
		}
		spans = append(spans, parentSpan{start: start, end: len(units)})
	}
	if len(units) == 0 {
		return nil, nil
	}

	texts := make([]string, len(units))
	for i := range units {
		texts[i] = units[i].text
	}
	vectors, err := s.EmbedTexts(ctx, embeddingCfg, texts, vectorSize)
	if err != nil {
		return nil, fmt.Errorf("embed sentences for parent-child chunking: %w", err)
	}
	if len(vectors) != len(units) {
		return nil, fmt.Errorf("embedding count mismatch: got %d, want %d", len(vectors), len(units))
	}
	for i := range units {
		units[i].vector = vectors[i]
	}

	// 3) 父文档内部语义切子文档
	chunks := make([]DocumentChunk, 0, len(units)/2+1)
	ordinal := 0
	integritySummary := make(map[string]int, 4)
	for parentIndex, span := range spans {
		if span.start >= span.end {
			continue
		}
		slice := units[span.start:span.end]
		parentID := fmt.Sprintf("%s-parent-%d", document.ID, parentIndex)
		parentText := joinSemanticUnits(slice)

		childTexts := buildChildTexts(slice, cfg.Child, cfg.ChildOverlapSentences)
		// 语义完整性检查 + 修复：把因单句超长而被迫切开的边界合并回去。
		// 正常情况下切分本身就落在句子边界，不会产生任何问题。
		childTexts, remaining := util.RepairChunkIntegrity(childTexts, cfg.Child.MaxSize)
		mergeIntegritySummary(integritySummary, util.SummarizeIntegrityIssues(remaining))

		for childIndex, childText := range childTexts {
			if strings.TrimSpace(childText) == "" {
				continue
			}
			chunks = append(chunks, DocumentChunk{
				ID:              fmt.Sprintf("%s-chunk-%d", document.ID, ordinal),
				KnowledgeBaseID: document.KnowledgeBaseID,
				DocumentID:      document.ID,
				DocumentName:    document.Name,
				Text:            childText,
				Index:           ordinal,
				Kind:            classifyDocumentChunkKind(childText),
				ParentID:        parentID,
				ParentIndex:     parentIndex,
				ChildIndex:      childIndex,
				ParentText:      parentText,
			})
			ordinal++
		}
	}

	if len(integritySummary) > 0 {
		log.Printf(
			"chunk integrity for %q: parents=%d children=%d remaining_issues=%v (无法修复的通常是单句本身超长)",
			document.Name, len(spans), ordinal, integritySummary,
		)
	}

	if len(chunks) == 0 {
		return nil, nil
	}

	// 结构化摘要块前置（与规则/语义分块路径保持一致的行为）
	summaryChunks := buildStructuredSummaryChunks(document, text, ordinal)
	return append(summaryFirstChunks(summaryChunks), chunks...), nil
}

// groupParagraphsIntoParents 把段落聚合成父文档。
// 当前父文档已达到目标长度，或再追加一个段落会超过硬上限时，收束当前父文档。
func groupParagraphsIntoParents(paragraphs [][]string, target, max int) [][][]string {
	if len(paragraphs) == 0 {
		return nil
	}
	if target <= 0 {
		target = defaultParentTargetSize
	}
	if max < target {
		max = target
	}

	groups := make([][][]string, 0, len(paragraphs)/3+1)
	current := make([][]string, 0, 4)
	currentLength := 0

	flush := func() {
		if len(current) == 0 {
			return
		}
		group := make([][]string, len(current))
		copy(group, current)
		groups = append(groups, group)
		current = current[:0]
		currentLength = 0
	}

	for _, sentences := range paragraphs {
		length := paragraphRuneLength(sentences)
		if length == 0 {
			continue
		}
		if len(current) > 0 && (currentLength >= target || currentLength+1+length > max) {
			flush()
		}
		current = append(current, sentences)
		currentLength += length
	}
	flush()
	return groups
}

func paragraphRuneLength(sentences []string) int {
	total := 0
	for index, sentence := range sentences {
		trimmed := strings.TrimSpace(sentence)
		if trimmed == "" {
			continue
		}
		if total > 0 {
			total++
		}
		_ = index
		total += util.RuneCount(trimmed)
	}
	return total
}

// splitOversizeParentBlocks 把超过硬上限的父文档按句子边界再切分成多个父文档。
//
// 必要性：从 PDF/网页提取的正文经常整篇没有空行（空行被归一），此时按段落
// 聚合会得到“整篇就是一个父文档”，失去父文档的意义（每个命中都会带回全篇）。
//
// 单个句子本身就超过上限时，先按窗口硬切，保证父文档长度严格有界。
func splitOversizeParentBlocks(blocks [][][]string, max int) [][][]string {
	if max <= 0 || len(blocks) == 0 {
		return blocks
	}

	type unit struct {
		text string
		para int
	}

	out := make([][][]string, 0, len(blocks))
	for _, block := range blocks {
		total := 0
		sentences := make([]unit, 0, 8)
		for paraIndex, sentencesOfPara := range block {
			for _, sentence := range sentencesOfPara {
				trimmed := strings.TrimSpace(sentence)
				if trimmed == "" {
					continue
				}
				// 超长单句先递归下探到更细的语义单元（子句 → 词 → 吸附式窗口）
				for _, window := range util.SplitRecursiveBySemanticUnits(trimmed, max) {
					sentences = append(sentences, unit{text: window, para: paraIndex})
					total += util.RuneCount(window) + 1
				}
			}
		}
		if total <= max || len(sentences) == 0 {
			out = append(out, block)
			continue
		}

		current := make([][]string, 0, 2)
		currentLength := 0
		currentPara := -1
		flush := func() {
			if len(current) == 0 {
				return
			}
			group := make([][]string, len(current))
			copy(group, current)
			out = append(out, group)
			current = current[:0]
			currentLength = 0
			currentPara = -1
		}
		for _, item := range sentences {
			length := util.RuneCount(item.text)
			if currentLength > 0 && currentLength+1+length > max {
				flush()
			}
			if item.para != currentPara {
				current = append(current, nil)
				currentPara = item.para
			}
			last := len(current) - 1
			current[last] = append(current[last], item.text)
			currentLength += length + 1
		}
		flush()
	}
	return out
}

// mergeIntegritySummary 把本轮问题计数累加到总汇总里。
func mergeIntegritySummary(dst map[string]int, src map[string]int) {
	for kind, count := range src {
		dst[kind] += count
	}
}

func joinSemanticUnits(units []semanticSentenceUnit) string {
	parts := make([]string, 0, len(units))
	for _, unit := range units {
		if trimmed := strings.TrimSpace(unit.text); trimmed != "" {
			parts = append(parts, trimmed)
		}
	}
	return util.JoinSemanticParts(parts...)
}

// buildChildTexts 在单个父文档内按语义相似度切分子文档。
//
// 处理链：
//  1. 按相邻句子的 embedding 相似度分组（语义相关性）；
//  2. 过短的组并回相邻组；
//  3. 相邻组之间按**完整句子**重叠（overlapSentences）；
//  4. 单句本身超限时递归下探到更细的语义单元（子句 → 词 → 吸附式窗口）。
//
// 子文档长度上限由 cfg.MaxSize（即原有的 maxChunkSize）控制。
func buildChildTexts(units []semanticSentenceUnit, cfg SemanticChunkByEmbeddingConfig, overlapSentences int) []string {
	if len(units) == 0 {
		return nil
	}
	if cfg.MaxSize <= 0 {
		cfg = DefaultSemanticChunkByEmbeddingConfig(defaultChunkSize)
	}
	if cfg.TargetSize <= 0 || cfg.TargetSize > cfg.MaxSize {
		cfg.TargetSize = cfg.MaxSize
	}
	if cfg.MinSize <= 0 || cfg.MinSize > cfg.TargetSize {
		cfg.MinSize = cfg.TargetSize / 2
	}
	if overlapSentences <= 0 {
		overlapSentences = defaultChildOverlapSentences
	}

	if len(units) == 1 {
		single := strings.TrimSpace(units[0].text)
		if single == "" {
			return nil
		}
		return util.SplitRecursiveBySemanticUnits(single, cfg.MaxSize)
	}

	similarities := make([]float64, len(units)-1)
	for i := 0; i+1 < len(units); i++ {
		similarities[i] = float64(cosineSimilarity(
			float64ToFloat32(units[i].vector),
			float64ToFloat32(units[i+1].vector),
		))
	}

	// 为「相邻块重叠」预留空间。
	// 若不预留，分组会紧贴 MaxSize，重叠句子永远放不下而被跳过，
	// 重叠形同虚设。这里按 (MaxSize - TargetSize) 预留，实际上就是
	// 让分组先收敛到目标长度，再让重叠占用上限与目标之间的余量。
	groupCfg := cfg
	if overlapSentences > 0 {
		reserve := cfg.MaxSize - cfg.TargetSize
		if reserve <= 0 {
			reserve = cfg.MaxSize / 5
		}
		if reduced := cfg.MaxSize - reserve; reduced >= cfg.MinSize && reduced >= cfg.TargetSize/2 {
			groupCfg.MaxSize = reduced
		}
	}
	if groupCfg.TargetSize > groupCfg.MaxSize {
		groupCfg.TargetSize = groupCfg.MaxSize
	}

	groups := groupSemanticUnits(units, similarities, groupCfg)
	// 过短块合并要用**真实上限**：这一步是修复碎片，如果也用预留后的上限，
	// 会出现「碎片既并不过去、又只能作为下一块的重叠重复一遍」的浪费。
	groups = mergeShortSemanticGroups(groups, units, similarities, cfg)
	// 重叠后仍以原始 cfg 的 MaxSize 作为硬上限
	groups = applySentenceOverlap(groups, units, cfg, overlapSentences)

	out := make([]string, 0, len(groups))
	for _, group := range groups {
		parts := make([]string, 0, len(group))
		for _, index := range group {
			parts = append(parts, units[index].text)
		}
		joined := util.JoinSemanticParts(parts...)
		if joined == "" {
			continue
		}
		// 仅当单句本身就超限时才会走到这里（分组本身已受 MaxSize 约束）
		if util.RuneCount(joined) > cfg.MaxSize {
			out = append(out, util.SplitRecursiveBySemanticUnits(joined, cfg.MaxSize)...)
			continue
		}
		out = append(out, joined)
	}
	return out
}

// applySentenceOverlap 让相邻子文档按「完整句子」重叠。
//
// 做法：把前一个子文档**末尾的 k 个完整句子**原样前置到当前子文档。
// 因为操作对象是句子而不是字符，重叠部分永远是完整句子，不会出现半句话；
// 若加上后超过 MaxSize，则依次减少重叠句数（最少 1 句）；仍放不下就不重叠。
//
// 注意：重叠取的是前一个子文档的**原始**句子集合，不会级联携带更早的重叠内容。
func applySentenceOverlap(
	groups [][]int,
	units []semanticSentenceUnit,
	cfg SemanticChunkByEmbeddingConfig,
	overlapSentences int,
) [][]int {
	if len(groups) <= 1 || overlapSentences <= 0 {
		return groups
	}

	out := make([][]int, len(groups))
	copy(out, groups)

	for i := 1; i < len(groups); i++ {
		previous := groups[i-1]
		current := groups[i]
		if len(previous) == 0 || len(current) == 0 {
			continue
		}
		currentLength := semanticGroupLength(current, units)
		maxTake := overlapSentences
		if maxTake > len(previous) {
			maxTake = len(previous)
		}

		take := 0
		for k := maxTake; k >= 1; k-- {
			overlap := previous[len(previous)-k:]
			if currentLength+1+semanticGroupLength(overlap, units) <= cfg.MaxSize {
				take = k
				break
			}
		}
		if take == 0 {
			continue
		}

		overlap := previous[len(previous)-take:]
		merged := make([]int, 0, take+len(current))
		merged = append(merged, overlap...)
		merged = append(merged, current...)
		out[i] = merged
	}

	return out
}

// expandRetrievedChunksToParents 把命中的子文档折叠为所属父文档：
// 同一父文档下的多个子文档只保留一个条目，正文替换为父文档全文，
// 分数取子文档中的最高分。没有父文档信息的块（如结构化摘要）原样保留。
func expandRetrievedChunksToParents(chunks []RetrievedChunk) []RetrievedChunk {
	if len(chunks) == 0 {
		return chunks
	}

	order := make([]string, 0, len(chunks))
	grouped := make(map[string]RetrievedChunk, len(chunks))
	standalone := make([]RetrievedChunk, 0)

	for _, chunk := range chunks {
		parentID := strings.TrimSpace(chunk.ParentID)
		parentText := strings.TrimSpace(chunk.ParentText)
		if parentID == "" || parentText == "" {
			standalone = append(standalone, chunk)
			continue
		}
		existing, ok := grouped[parentID]
		if !ok {
			order = append(order, parentID)
			grouped[parentID] = buildParentChunk(chunk, parentID, parentText)
			continue
		}
		if chunk.Score > existing.Score {
			grouped[parentID] = buildParentChunk(chunk, parentID, parentText)
		}
	}

	expanded := make([]RetrievedChunk, 0, len(order)+len(standalone))
	for _, parentID := range order {
		expanded = append(expanded, grouped[parentID])
	}
	expanded = append(expanded, standalone...)

	sortRetrievedChunksByScore(expanded)
	return expanded
}

// buildParentChunk 用父文档正文构造对外返回的检索块，同时保留子文档溯源信息。
func buildParentChunk(child RetrievedChunk, parentID, parentText string) RetrievedChunk {
	return RetrievedChunk{
		DocumentChunk: DocumentChunk{
			ID:              parentID,
			KnowledgeBaseID: child.KnowledgeBaseID,
			DocumentID:      child.DocumentID,
			DocumentName:    child.DocumentName,
			Text:            parentText,
			Index:           child.ParentIndex,
			Kind:            child.Kind,
			ParentID:        parentID,
			ParentIndex:     child.ParentIndex,
			ChildIndex:      child.ChildIndex,
			ParentText:      parentText,
			ChildID:         child.ID,
		},
		Score:             child.Score,
		RawScore:          child.RawScore,
		RetrievalChannels: child.RetrievalChannels,
		DenseRank:         child.DenseRank,
		SparseRank:        child.SparseRank,
	}
}

func sortRetrievedChunksByScore(chunks []RetrievedChunk) {
	sort.SliceStable(chunks, func(i, j int) bool {
		return lessRetrievedChunk(chunks[i], chunks[j])
	})
}

func lessRetrievedChunk(a, b RetrievedChunk) bool {
	if a.Score != b.Score {
		return a.Score > b.Score
	}
	if a.DocumentID != b.DocumentID {
		return a.DocumentID < b.DocumentID
	}
	return a.Index < b.Index
}
