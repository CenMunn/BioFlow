package util

import (
	"regexp"
	"strings"
	"unicode"
	"unicode/utf8"
)

// AnaphoraResult 指代消解结果。
type AnaphoraResult struct {
	Text          string
	Replacements  int    // 完成的代词替换次数
	DocumentTopic string // 从标题提取的主题实体（无则空）
}

// englishSentenceAnaphors 句首可消解的英文代词/指示代词。
var englishSentenceAnaphors = map[string]struct{}{
	"it": {}, "they": {}, "them": {}, "this": {}, "these": {}, "those": {},
	"its": {}, "their": {}, "such": {}, "he": {}, "she": {}, "him": {}, "her": {},
}

// englishStandaloneFollowers 当代词后面紧跟这些词或标点时，说明代词是独立使用
// （而非 "This study"、"These findings" 这种自带中心名词的搭配），此时才可安全替换。
var englishStandaloneFollowers = map[string]struct{}{
	"is": {}, "are": {}, "was": {}, "were": {}, "be": {}, "been": {},
	"has": {}, "have": {}, "had": {},
	"can": {}, "could": {}, "may": {}, "might": {}, "must": {}, "cannot": {},
	"will": {}, "would": {}, "should": {}, "shall": {},
	"does": {}, "do": {}, "did": {},
	"suggest": {}, "suggests": {}, "suggested": {},
	"indicate": {}, "indicates": {}, "indicated": {},
	"show": {}, "shows": {}, "showed": {}, "shown": {},
	"demonstrate": {}, "demonstrates": {}, "demonstrated": {},
	"reveal": {}, "reveals": {}, "revealed": {},
	"play": {}, "plays": {}, "played": {},
	"remain": {}, "remains": {}, "remained": {},
	"lead": {}, "leads": {}, "led": {},
	"result": {}, "results": {}, "resulted": {},
	"appear": {}, "appears": {}, "appeared": {},
	"cause": {}, "causes": {}, "caused": {},
	"contribute": {}, "contributes": {}, "contributed": {},
	"include": {}, "includes": {}, "included": {},
	"provide": {}, "provides": {}, "provided": {},
	"exhibit": {}, "exhibits": {}, "exhibited": {},
	"promote": {}, "promotes": {}, "promoted": {},
	"reduce": {}, "reduces": {}, "reduced": {},
	"increase": {}, "increases": {}, "increased": {},
	"decrease": {}, "decreases": {}, "decreased": {},
	"affect": {}, "affects": {}, "affected": {},
	"represent": {}, "represents": {}, "represented": {},
	"correlate": {}, "correlates": {}, "correlated": {},
	"differ": {}, "differs": {}, "differed": {},
	"improve": {}, "improves": {}, "improved": {},
	"support": {}, "supports": {}, "supported": {},
	"isn't": {}, "aren't": {}, "wasn't": {}, "weren't": {},
	"also": {}, "however": {}, "therefore": {}, "thus": {}, "moreover": {},
}

// 中文句首人称代词（只处理真正的代词，"该/其/此" 属于限定词，替换会破坏语义）。
var chineseSentenceAnaphors = []string{"它们", "它"}

// 中文领域名词后缀，用于识别可作先行词的实体。
var chineseEntitySuffixes = []string{
	"症", "病", "菌", "群", "细胞", "基因", "蛋白", "受体", "治疗", "干预",
	"人群", "儿童", "患者", "模型", "研究", "分析", "水平", "丰度", "障碍",
	"紊乱", "失调", "炎症", "代谢", "通路", "因子", "效应", "机制",
}

var (
	// 由 chineseEntitySuffixes 拼装，避免后缀列表与正则两处维护。
	reChineseEntity = regexp.MustCompile(
		`[\p{Han}]{2,8}(` + strings.Join(chineseEntitySuffixes, "|") + `)`)
	reParenthetical = regexp.MustCompile(`\(([A-Z][A-Za-z0-9-]{1,11})\)`)
)

// ResolveAnaphora 用规则消解句首代词，把代词替换为明确的实体名，
// 以增强分块后文本的语义完整性（分块会切断上下文，代词失去所指）。
//
// 策略（保守、高精度优先）：
//  1. 从文档标题提取主题实体作为兜底先行词；
//  2. 逐段落扫描，持续更新「最近提到的实体」；
//  3. 仅替换位于句子开头、且确为独立使用的代词（英文要求后接动词/系动词/标点，
//     中文只处理 "它/它们"）；
//  4. 句子中段出现的代词一律不动，避免改写原意。
//
// 返回替换次数，便于日志评估。
func ResolveAnaphora(text, documentTitle string) AnaphoraResult {
	result := AnaphoraResult{Text: text}
	if strings.TrimSpace(text) == "" {
		return result
	}

	topicEntities := extractTitleEntities(documentTitle)
	result.DocumentTopic = firstEntity(topicEntities)

	paragraphs := splitParagraphs(text)
	if len(paragraphs) == 0 {
		return result
	}

	replaced := 0
	output := make([]string, 0, len(paragraphs))
	lastEntity := result.DocumentTopic

	for _, paragraph := range paragraphs {
		flattened := strings.Join(strings.Fields(strings.ReplaceAll(paragraph, "\n", " ")), " ")
		if flattened == "" {
			continue
		}
		sentences := splitSentences(flattened, false)
		rewritten := make([]string, 0, len(sentences))
		for _, sentence := range sentences {
			trimmedSentence := strings.TrimSpace(sentence)
			if trimmedSentence == "" {
				continue
			}
			// 先消解（使用「上一句为止」的先行词）
			if lastEntity != "" {
				updated, changed := replaceSentenceInitialAnaphor(trimmedSentence, lastEntity)
				if changed {
					trimmedSentence = updated
					replaced++
				}
			}
			rewritten = append(rewritten, trimmedSentence)
			// 再用本句新出现的实体更新先行词
			if entity := mostSalientEntity(trimmedSentence); entity != "" {
				lastEntity = entity
			}
		}
		if len(rewritten) > 0 {
			output = append(output, strings.Join(rewritten, " "))
		}
	}

	result.Replacements = replaced
	result.Text = strings.Join(output, "\n\n")
	return result
}

// replaceSentenceInitialAnaphor 替换句首独立代词，返回替换后文本与是否发生替换。
func replaceSentenceInitialAnaphor(sentence, antecedent string) (string, bool) {
	trimmed := strings.TrimSpace(sentence)
	if trimmed == "" || strings.TrimSpace(antecedent) == "" {
		return sentence, false
	}

	// 中文
	for _, anaphor := range chineseSentenceAnaphors {
		if !strings.HasPrefix(trimmed, anaphor) {
			continue
		}
		rest := strings.TrimSpace(strings.TrimPrefix(trimmed, anaphor))
		if rest == "" {
			continue
		}
		// 要求后接动词性成分或标点，避免 "它们（菌群）" 这类同位语被误替换
		next, _ := firstRune(rest)
		if !unicode.Is(unicode.Han, next) {
			continue
		}
		return antecedent + rest, true
	}

	// 英文：取句首 token
	tokens := strings.Fields(trimmed)
	if len(tokens) < 2 {
		return sentence, false
	}
	head := strings.ToLower(strings.Trim(tokens[0], `"'([{`))
	if _, ok := englishSentenceAnaphors[head]; !ok {
		return sentence, false
	}
	follower := strings.ToLower(strings.Trim(tokens[1], `.,;:!?"'()[]{}–—-`))
	if follower == "" {
		// 代词后就是标点（如 "It, however, ..."），视为独立使用
		return antecedent + " " + strings.Join(tokens[1:], " "), true
	}
	if _, ok := englishStandaloneFollowers[follower]; !ok {
		return sentence, false
	}
	return antecedent + " " + strings.Join(tokens[1:], " "), true
}

// extractTitleEntities 从文档标题提取主题实体候选。
func extractTitleEntities(title string) []string {
	trimmed := strings.TrimSpace(title)
	if trimmed == "" {
		return nil
	}
	// 去掉扩展名与常见分隔符，保留语义片段
	trimmed = strings.TrimSuffix(trimmed, ".txt")
	trimmed = strings.TrimSuffix(trimmed, ".pdf")
	trimmed = strings.ReplaceAll(trimmed, "_", " ")
	trimmed = strings.ReplaceAll(trimmed, "-", " ")

	candidates := make([]string, 0, 4)
	// 标题里的缩写（如 ... in ASD (2023)）
	for _, match := range reParenthetical.FindAllStringSubmatch(trimmed, -1) {
		if len(match) > 1 && isAcronym(match[1]) {
			candidates = append(candidates, match[1])
		}
	}
	// 标题主体：截断到冒号前，取前若干词
	main := trimmed
	if idx := strings.IndexAny(main, ":："); idx > 0 {
		if head := strings.TrimSpace(main[:idx]); runeCount(head) >= 6 {
			main = head
		}
	}
	if runeCount(main) > 0 && runeCount(main) <= 160 {
		candidates = append(candidates, main)
	}
	return candidates
}

func firstEntity(candidates []string) string {
	for _, candidate := range candidates {
		if trimmed := strings.TrimSpace(candidate); trimmed != "" {
			return trimmed
		}
	}
	return ""
}

// mostSalientEntity 返回句子中最适合充当先行词的实体。
//
// 取「句内首个实体」而非末个：句首实体通常是该句主语，也就是话语话题；
// 若取末个匹配，容易把 "肠道菌群失调在自闭症儿童中…" 这种句子里
// 作状语的介词短语（在自闭症儿童）当成先行词。跨句的新旧程度由调用方
// 逐句更新 lastEntity 来保证。
func mostSalientEntity(sentence string) string {
	if entity := firstChineseEntity(sentence); entity != "" {
		return entity
	}

	// 英文：首个大写开头的专名词组或全大写缩写
	tokens := strings.Fields(sentence)
	run := make([]string, 0, 4)
	for _, token := range tokens {
		bare := strings.Trim(token, `"'()[]{}.,;:`)
		if isCapitalizedWord(bare) {
			run = append(run, bare)
			continue
		}
		if len(run) == 0 {
			continue
		}
		if candidate := joinEntityRun(run); candidate != "" {
			return candidate
		}
		run = run[:0]
	}
	return joinEntityRun(run)
}

// joinEntityRun 判断一段大写开头的词序列是否构成专名。
// 单大写词不算（可能只是句首普通单词），除非是全大写缩写。
func joinEntityRun(run []string) string {
	if len(run) == 0 {
		return ""
	}
	candidate := strings.TrimRight(strings.Join(run, " "), ".,;:")
	if isAcronym(candidate) || len(run) >= 2 {
		return candidate
	}
	return ""
}

// chineseEntityLeadTrim 需要从实体匹配左侧剔除的虚词/介词。
const chineseEntityLeadTrim = "在对于由从与和为把被是的了有将向给跟同以"

// firstChineseEntity 返回句内首个领域实体。
// 跳过落在更长词组内部的匹配（如 "在自闭症儿童" 中的 "自闭症儿童"），
// 并剔除前导虚词。
func firstChineseEntity(sentence string) string {
	for _, span := range reChineseEntity.FindAllStringIndex(sentence, -1) {
		if span[0] > 0 {
			prev, _ := utf8.DecodeLastRuneInString(sentence[:span[0]])
			if unicode.Is(unicode.Han, prev) {
				continue
			}
		}
		match := sentence[span[0]:span[1]]
		trimmed := strings.TrimLeftFunc(match, func(r rune) bool {
			return strings.ContainsRune(chineseEntityLeadTrim, r)
		})
		if runeCount(trimmed) >= 2 {
			return trimmed
		}
	}
	return ""
}

func isCapitalizedWord(word string) bool {
	if word == "" {
		return false
	}
	runes := []rune(word)
	if !unicode.IsUpper(runes[0]) {
		return false
	}
	return true
}

// isAcronym 判断是否为全大写缩写（>=2 个字母），如 ASD、FMT、16S。
func isAcronym(word string) bool {
	letters := 0
	for _, r := range word {
		switch {
		case unicode.IsUpper(r):
			letters++
		case unicode.IsDigit(r), r == '-':
			continue
		default:
			return false
		}
	}
	return letters >= 2
}

func firstRune(text string) (rune, bool) {
	for _, r := range text {
		return r, true
	}
	return 0, false
}
