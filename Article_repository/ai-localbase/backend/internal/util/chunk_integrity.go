package util

import (
	"regexp"
	"strconv"
	"strings"
	"unicode"
)

// ChunkIntegrityIssue 描述一个分块在语义完整性上的问题。
type ChunkIntegrityIssue struct {
	Index  int
	Kind   string
	Detail string
}

// 问题类型。
const (
	// IssueEndsMidSentence 前一块没有以句末标点收尾 —— 说明分块边界切在了句子中间。
	IssueEndsMidSentence = "ends_mid_sentence"
	// IssueStartsMidSentence 当前块是从句子中间开始的（与上一条是同一个边界的另一面）。
	IssueStartsMidSentence = "starts_mid_sentence"
	// IssueUnbalancedBrackets 括号不配对。
	IssueUnbalancedBrackets = "unbalanced_brackets"
	// IssueUnbalancedQuotes 引号不配对。
	IssueUnbalancedQuotes = "unbalanced_quotes"
	// IssueDanglingConnector 块以承接性连接词开头（本身自带中心语义时可接受，仅作提示）。
	IssueDanglingConnector = "dangling_connector"
)

// boundaryMinRunes：只有「够长的正文块」之间的边界才值得判定。
// 标题、表头、编号等短行天然不带句末标点，不应被误判为切断句子。
const boundaryMinRunes = 24

// 可作为「合法收尾」的标点：句末标点，以及冒号（列举/标题的收尾）。
func isAcceptableChunkTail(r rune) bool {
	if isSentencePunctuation(r) {
		return true
	}
	switch r {
	case '：', ':', '；', ';':
		return true
	default:
		return false
	}
}

var closingRunes = `"'”’〞)]}）】」』》〉`

func isClosingRune(r rune) bool {
	return strings.ContainsRune(closingRunes, r)
}

// endsWithSentenceTerminator 判断文本是否以句末标点收尾
// （允许句末标点后跟闭合引号/括号，如 `...end."`）。
func endsWithSentenceTerminator(text string) bool {
	trimmed := strings.TrimSpace(text)
	if trimmed == "" {
		return false
	}
	runes := []rune(trimmed)
	index := len(runes) - 1
	for index >= 0 && isClosingRune(runes[index]) {
		index--
	}
	if index < 0 {
		return false
	}
	return isAcceptableChunkTail(runes[index])
}

var (
	structuredSummaryPrefix = "统计摘要："
	structuredRowPattern    = regexp.MustCompile(`第\d+行：`)
)

// isStructuredChunk 结构化表格块（统计摘要 / 第N行）自带完整结构，
// 不适用"句末标点"判定。
func isStructuredChunk(text string) bool {
	trimmed := strings.TrimSpace(text)
	if strings.HasPrefix(trimmed, structuredSummaryPrefix) {
		return true
	}
	return structuredRowPattern.MatchString(trimmed)
}

// 承接性连接词：出现在块首说明这块很可能是上一块的延续。
var englishDanglingConnectors = []string{
	"and ", "but ", "or ", "nor ", "so ", "then ", "yet ",
	"however", "therefore", "thus", "moreover", "furthermore", "hence",
	"also", "because", "although", "whereas", "besides", "meanwhile",
	"in addition", "as well as", "for example", "for instance",
	"on the other hand", "in contrast", "that is", "in other words",
}

var chineseDanglingConnectors = []string{
	"而且", "但是", "然而", "因此", "所以", "此外", "另外", "同时",
	"不过", "并且", "以及", "由此", "据此", "总之", "综上", "换言之",
}

func startsWithDanglingConnector(text string) bool {
	trimmed := strings.TrimSpace(text)
	if trimmed == "" {
		return false
	}
	lowered := strings.ToLower(trimmed)
	for _, connector := range englishDanglingConnectors {
		if strings.HasPrefix(lowered, connector) {
			return true
		}
	}
	for _, connector := range chineseDanglingConnectors {
		if strings.HasPrefix(trimmed, connector) {
			return true
		}
	}
	return false
}

// bracketPairs 参与配对检查的括号对（左右成对出现）。
var bracketPairs = [][2]rune{
	{'(', ')'}, {'[', ']'}, {'{', '}'},
	{'（', '）'}, {'【', '】'}, {'「', '」'}, {'『', '』'}, {'《', '》'},
}

// CheckChunkIntegrity 检查各分块的语义完整性。
//
// 检查项：
//  1. 边界完整性：前一块是否以句末标点收尾（否则说明边界切在句子中间）；
//  2. 括号配对：中英文括号是否成对；
//  3. 引号配对：双引号与中文引号是否成对；
//  4. 悬挂连接词：块首是否为承接性连接词（提示性，不自动合并）。
func CheckChunkIntegrity(chunks []string) []ChunkIntegrityIssue {
	issues := make([]ChunkIntegrityIssue, 0)
	for index, chunk := range chunks {
		trimmed := strings.TrimSpace(chunk)
		if trimmed == "" {
			continue
		}

		// 1. 边界完整性（与上一块组成同一个边界）
		if index > 0 {
			previous := strings.TrimSpace(chunks[index-1])
			if shouldJudgeBoundary(previous, trimmed) && !endsWithSentenceTerminator(previous) {
				issues = append(issues, ChunkIntegrityIssue{
					Index:  index - 1,
					Kind:   IssueEndsMidSentence,
					Detail: tailSnippet(previous, 24),
				})
				issues = append(issues, ChunkIntegrityIssue{
					Index:  index,
					Kind:   IssueStartsMidSentence,
					Detail: headSnippet(trimmed, 24),
				})
			}
		}

		// 2. 括号配对
		for _, pair := range bracketPairs {
			if open, close := strings.Count(trimmed, string(pair[0])), strings.Count(trimmed, string(pair[1])); open != close {
				issues = append(issues, ChunkIntegrityIssue{
					Index:  index,
					Kind:   IssueUnbalancedBrackets,
					Detail: strings.TrimSpace(string(pair[0])) + "/" + strings.TrimSpace(string(pair[1])) + " 不配对",
				})
			}
		}

		// 3. 引号配对
		if strings.Count(trimmed, `"`)%2 != 0 {
			issues = append(issues, ChunkIntegrityIssue{
				Index: index, Kind: IssueUnbalancedQuotes, Detail: `" 数量为奇数`,
			})
		}
		if strings.Count(trimmed, "“") != strings.Count(trimmed, "”") {
			issues = append(issues, ChunkIntegrityIssue{
				Index: index, Kind: IssueUnbalancedQuotes, Detail: "中文双引号不配对",
			})
		}

		// 4. 悬挂连接词（提示性）
		if index > 0 && startsWithDanglingConnector(trimmed) && !isStructuredChunk(trimmed) {
			issues = append(issues, ChunkIntegrityIssue{
				Index: index, Kind: IssueDanglingConnector, Detail: headSnippet(trimmed, 18),
			})
		}
	}
	return issues
}

// shouldJudgeBoundary 判断这两个块的边界是否值得判定为"切断句子"。
// 短行（标题/表头/编号）与结构化块不参与判定，避免误报。
func shouldJudgeBoundary(previous, current string) bool {
	if runeCount(previous) < boundaryMinRunes {
		return false
	}
	if isStructuredChunk(previous) || isStructuredChunk(current) {
		return false
	}
	// 上一块本身是"独立成条"的短结构（例如以冒号收尾的列表头）时跳过
	if strings.HasSuffix(previous, "：") || strings.HasSuffix(previous, ":") {
		return false
	}
	return true
}

// RepairChunkIntegrity 尝试修复边界不完整的分块：把「从句子中间开始」的块
// 并入前一块，合并后长度不超过 maxSize 时才执行。
//
// 返回修复后的分块与**仍然存在**的问题（无法合并的边界、括号/引号不配对等）。
func RepairChunkIntegrity(chunks []string, maxSize int) ([]string, []ChunkIntegrityIssue) {
	if len(chunks) <= 1 {
		return chunks, CheckChunkIntegrity(chunks)
	}

	repaired := make([]string, 0, len(chunks))
	for _, chunk := range chunks {
		trimmed := strings.TrimSpace(chunk)
		if trimmed == "" {
			continue
		}
		if len(repaired) == 0 {
			repaired = append(repaired, trimmed)
			continue
		}
		previous := repaired[len(repaired)-1]
		if shouldMergeBoundary(previous, trimmed, maxSize) {
			repaired[len(repaired)-1] = previous + " " + trimmed
			continue
		}
		repaired = append(repaired, trimmed)
	}

	return repaired, CheckChunkIntegrity(repaired)
}

// shouldMergeBoundary 判断 current 是否应并入 previous。
func shouldMergeBoundary(previous, current string, maxSize int) bool {
	if !shouldJudgeBoundary(previous, current) {
		return false
	}
	if endsWithSentenceTerminator(previous) {
		return false
	}
	if maxSize > 0 && runeCount(previous)+1+runeCount(current) > maxSize {
		// 合并会超限，只能保留这个不完整边界（交由调用方记录问题）
		return false
	}
	return true
}

// SummarizeIntegrityIssues 汇总问题类型计数，便于日志输出。
func SummarizeIntegrityIssues(issues []ChunkIntegrityIssue) map[string]int {
	summary := make(map[string]int, 4)
	for _, issue := range issues {
		summary[issue.Kind]++
	}
	return summary
}

func headSnippet(text string, limit int) string {
	return runeTruncate(strings.TrimSpace(text), limit)
}

// runeTruncate 按 rune 截断并加省略号。
func runeTruncate(text string, limit int) string {
	runes := []rune(text)
	if limit <= 0 || len(runes) <= limit {
		return text
	}
	return string(runes[:limit]) + "…"
}

func tailSnippet(text string, limit int) string {
	trimmed := strings.TrimSpace(text)
	runes := []rune(trimmed)
	if len(runes) <= limit {
		return trimmed
	}
	return "…" + string(runes[len(runes)-limit:])
}

// IsCompleteSentenceTail 供外部复用：判断文本是否以完整句子收尾。
func IsCompleteSentenceTail(text string) bool {
	return endsWithSentenceTerminator(text)
}

// HasSentenceInternalBreak 判断文本是否含有句末标点（即由多个句子组成）。
func HasSentenceInternalBreak(text string) bool {
	for _, r := range text {
		if isSentencePunctuation(r) {
			return true
		}
	}
	return false
}

// sentenceEndPositions 返回所有句子结束下标（即下一句的起始位置）。
// 复用 sentenceEndAfter，保证与 splitSentences 的句子边界规则完全一致
// —— 否则中文（标点后无空格）会被判定为"没有句子边界"。
func sentenceEndPositions(runes []rune) []int {
	positions := make([]int, 0, 8)
	for i := 0; i < len(runes); i++ {
		end, ok := sentenceEndAfter(runes, i)
		if !ok {
			continue
		}
		positions = append(positions, end)
		i = end - 1
	}
	return positions
}

// trailingSentenceStart 返回文本中「最后 n 个句子」的起始下标。
//
// 边界数组记录的是每句结束后的位置；要取最后 n 句，起点应当是
// 倒数第 n+1 个边界（即第 n 句的句首）。句子数不足时返回 0（表示整段）。
func trailingSentenceStart(text string, sentences int) int {
	if sentences <= 0 {
		return runeCount(text)
	}
	runes := []rune(text)
	boundaries := sentenceEndPositions(runes)
	if len(boundaries) < sentences+1 {
		return 0
	}
	start := boundaries[len(boundaries)-sentences-1]
	for start < len(runes) && unicode.IsSpace(runes[start]) {
		start++
	}
	return start
}

// TrailingSentences 取出文本末尾 n 个完整句子。
// 不足 n 句时返回整个文本；sentences<=0 或文本为空时返回空串。
func TrailingSentences(text string, sentences int) string {
	trimmed := strings.TrimSpace(text)
	if trimmed == "" || sentences <= 0 {
		return ""
	}
	runes := []rune(trimmed)
	start := trailingSentenceStart(trimmed, sentences)
	if start <= 0 || start >= len(runes) {
		return trimmed
	}
	return strings.TrimSpace(string(runes[start:]))
}

// DescribeIntegrityIssue 生成可读的问题描述（用于日志）。
func DescribeIntegrityIssue(issue ChunkIntegrityIssue) string {
	return "chunk#" + strconv.Itoa(issue.Index) + " " + issue.Kind + ": " + issue.Detail
}
