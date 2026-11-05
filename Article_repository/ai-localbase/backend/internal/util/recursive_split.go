package util

import (
	"strings"
	"unicode"
)

// 语义单元层级，由粗到细。
//
// 递归切分的核心约定：**优先在更粗的语义边界上断开**。
// 只有当某一级的所有单元仍然超过长度上限时，才下探到下一级。
// 因此「不切断句子」是默认行为，只有在单句本身就超限（例如没有句末标点的
// 长段落、OCR 结果）时才会逐级退化到子句 → 词 → 字符窗口。
var semanticSplitLevels = []func(string) []string{
	splitParagraphLevel,
	splitSentenceLevel,
	splitClauseLevel,
	splitWordLevel,
}

// SplitRecursiveBySemanticUnits 按语义单元由粗到细递归切分文本。
//
// 保证：
//   - 任何长度不超过 limit 的块都不会在句子内部被切断；
//   - 相邻的短语义单元会被重新合并，避免产出大量碎片；
//   - 即使文本完全没有标点，也会吸附到最近的合法断点（空格/标点）再硬切，
//     不会在单词中间断开（除非单个"词"本身就超过 limit）。
func SplitRecursiveBySemanticUnits(text string, limit int) []string {
	trimmed := strings.TrimSpace(text)
	if trimmed == "" {
		return nil
	}
	if limit <= 0 {
		return []string{trimmed}
	}
	if runeCount(trimmed) <= limit {
		return []string{trimmed}
	}
	return splitRecursive(trimmed, limit, 0)
}

func splitRecursive(text string, limit int, depth int) []string {
	trimmed := strings.TrimSpace(text)
	if trimmed == "" {
		return nil
	}
	if runeCount(trimmed) <= limit {
		return []string{trimmed}
	}
	if depth >= len(semanticSplitLevels) {
		// 语义单元已用尽，退化为「吸附式窗口切分」：仍尽量避开单词内部
		return forceWindowSplitAligned(trimmed, limit)
	}

	parts := semanticSplitLevels[depth](trimmed)
	if len(parts) <= 1 {
		// 该级切不开，直接下探
		return splitRecursive(trimmed, limit, depth+1)
	}

	units := make([]string, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		if runeCount(part) <= limit {
			units = append(units, part)
			continue
		}
		units = append(units, splitRecursive(part, limit, depth+1)...)
	}
	if len(units) == 0 {
		return nil
	}
	// 递归可能产出大量短单元，合并回接近上限的块
	return mergeSemanticUnits(units, limit)
}

// mergeSemanticUnits 贪心合并相邻语义单元，直到再加一个就会超过上限。
func mergeSemanticUnits(units []string, limit int) []string {
	out := make([]string, 0, len(units))
	current := ""
	for _, unit := range units {
		trimmed := strings.TrimSpace(unit)
		if trimmed == "" {
			continue
		}
		if current == "" {
			current = trimmed
			continue
		}
		candidate := JoinSemanticParts(current, trimmed)
		if runeCount(candidate) <= limit {
			current = candidate
			continue
		}
		out = append(out, current)
		current = trimmed
	}
	if current != "" {
		out = append(out, current)
	}
	return out
}

// JoinSemanticParts 拼接语义片段：仅在必要处插入空格。
//
// 中文句子之间不应插入空格（原文是 "句子一。句子二。"，而不是
// "句子一。 句子二。"），而英文单词与句子之间必须有空格。
// 否则会给中文正文引入原文并不存在的空白，以及给英文引入粘连（"end.Next"）。
func JoinSemanticParts(parts ...string) string {
	var builder strings.Builder
	lastRune := rune(0)
	for _, part := range parts {
		trimmed := strings.TrimSpace(part)
		if trimmed == "" {
			continue
		}
		first, _ := firstRuneOf(trimmed)
		if builder.Len() > 0 && needsSpaceBetween(lastRune, first) {
			builder.WriteRune(' ')
		}
		builder.WriteString(trimmed)
		lastRune = lastRuneOf(trimmed)
	}
	return builder.String()
}

// needsSpaceBetween 判断两个相邻字符之间是否必须插入空格。
func needsSpaceBetween(prev, next rune) bool {
	if prev == 0 || next == 0 {
		return false
	}
	// 涉及中日韩字符/全角标点时，按原文不插空格
	if isCJKOrFullWidth(prev) || isCJKOrFullWidth(next) {
		return false
	}
	// 下一个字符本身是句末/子句标点或收尾符号时，紧贴前文
	if isSentencePunctuation(next) || isClausePunctuation(next) || isClosingRune(next) {
		return false
	}
	return true
}

func firstRuneOf(text string) (rune, bool) {
	for _, r := range text {
		return r, true
	}
	return 0, false
}

func lastRuneOf(text string) rune {
	var last rune
	for _, r := range text {
		last = r
	}
	return last
}

// ── 各级语义单元 ────────────────────────────────────────────────────────────

func splitParagraphLevel(text string) []string {
	return splitParagraphs(text)
}

// splitSentenceLevel 按句末标点切分。
// 段内的硬换行（PDF 断行）先归一为空格，避免把句子切成碎片。
func splitSentenceLevel(text string) []string {
	flattened := flattenLineBreaks(text)
	return splitSentences(flattened, false)
}

// splitClauseLevel 按子句级标点切分（分号、逗号、顿号）。
// 仅在句子本身超限时使用，保证切点仍在"语义上还算完整"的位置。
func splitClauseLevel(text string) []string {
	flattened := flattenLineBreaks(text)
	runes := []rune(flattened)
	out := make([]string, 0, 8)
	start := 0
	for i := 0; i < len(runes); i++ {
		if !isClausePunctuation(runes[i]) {
			continue
		}
		// 标点后必须跟空白/引号/结尾，避免切在 "3.5"、"e.g."、"Fig. 2" 内部
		if i+1 < len(runes) {
			next := runes[i+1]
			if !unicode.IsSpace(next) && next != '"' && next != '\'' {
				continue
			}
		}
		segment := strings.TrimSpace(string(runes[start : i+1]))
		if segment != "" {
			out = append(out, segment)
		}
		start = i + 1
	}
	tail := strings.TrimSpace(string(runes[start:]))
	if tail != "" {
		out = append(out, tail)
	}
	return out
}

// splitWordLevel 退化为按空白切分，保证不会把单词劈成两半。
func splitWordLevel(text string) []string {
	return strings.Fields(flattenLineBreaks(text))
}

func flattenLineBreaks(text string) string {
	if !strings.ContainsAny(text, "\n\r\t") {
		return text
	}
	return strings.Join(strings.FieldsFunc(text, func(r rune) bool {
		return r == '\n' || r == '\r' || r == '\t'
	}), " ")
}

func isClausePunctuation(r rune) bool {
	switch r {
	case '；', ';', '，', ',', '、':
		return true
	default:
		return false
	}
}

// isBreakFriendlyPunctuation 可作为「窗口取整」吸附点的标点。
func isBreakFriendlyPunctuation(r rune) bool {
	switch r {
	case '。', '！', '？', '.', '!', '?', '；', ';', '，', ',', '、',
		':', '：', ')', ']', '}', '）', '】', '」', '』', '”', '\'', '"':
		return true
	default:
		return false
	}
}

// ── 兜底：吸附式窗口切分 ────────────────────────────────────────────────────

// forceWindowSplitAligned 按窗口硬切，但把切点向左吸附到最近的合法断点
// （空格或标点），最多回退窗口长度的 1/5。
// 这样即使文本完全没有标点，也不会在单词中间断开。
func forceWindowSplitAligned(text string, limit int) []string {
	if limit <= 0 {
		return []string{text}
	}
	runes := []rune(text)
	if len(runes) <= limit {
		return []string{text}
	}

	parts := make([]string, 0, len(runes)/limit+1)
	start := 0
	for start < len(runes) {
		if len(runes)-start <= limit {
			tail := strings.TrimSpace(string(runes[start:]))
			if tail != "" {
				parts = append(parts, tail)
			}
			break
		}
		cut := alignCutPoint(runes, start+limit, start, limit)
		segment := strings.TrimSpace(string(runes[start:cut]))
		if segment == "" {
			// 兜底：吸附点退过了起点，直接硬切
			cut = start + limit
			segment = strings.TrimSpace(string(runes[start:cut]))
		}
		if segment != "" {
			parts = append(parts, segment)
		}
		start = cut
	}
	return parts
}

// alignCutPoint 把切点向左吸附到最近的合法断点。
// 找不到时返回原切点（宁可硬切，也不要产出空块）。
func alignCutPoint(runes []rune, cut, start, limit int) int {
	if cut > len(runes) {
		cut = len(runes)
	}
	minCut := cut - limit/5
	if minCut <= start {
		minCut = start + 1
	}
	for i := cut; i > minCut; i-- {
		prev := runes[i-1]
		if unicode.IsSpace(prev) || isBreakFriendlyPunctuation(prev) {
			return i
		}
	}
	return cut
}
