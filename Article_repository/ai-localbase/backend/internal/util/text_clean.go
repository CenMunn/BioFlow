package util

import (
	"html"
	"regexp"
	"strings"
	"unicode"
)

// CleanStats 记录文本清洗过程中移除/归一化的噪声量，
// 用于日志留痕与预处理效果评估。
type CleanStats struct {
	HTMLTagsRemoved   int
	HTMLEntitiesFixed int
	ControlRunesDrop  int
	UnicodeNormalized int
	BoilerplateLines  int
	ReferencesTrimmed bool
	OriginalRunes     int
	CleanedRunes      int
}

// 只匹配「像标签」的结构，避免误伤数学表达式（如 p < 0.05、a < b）。
//   - 成对丢弃 script/style 等整块
//   - <tag ...>、<tag/>、</tag>、<!-- ... -->
var (
	reHTMLOpen  = regexp.MustCompile(`<[a-zA-Z][a-zA-Z0-9:_-]*(\s[^<>]*)?/?>`)
	reHTMLClose = regexp.MustCompile(`</[a-zA-Z][a-zA-Z0-9:_-]*\s*>`)
	reHTMLComm  = regexp.MustCompile(`(?s)<!--.*?-->`)
	reHTMLEnt   = regexp.MustCompile(`&(#[0-9]{2,7}|#[xX][0-9a-fA-F]{2,6}|[a-zA-Z][a-zA-Z0-9]{1,31});`)
)

// Go 的 RE2 语法不支持反向引用（\1），因此按标签名逐个编译整块匹配。
var reHTMLBlocks = func() []*regexp.Regexp {
	names := []string{"script", "style", "noscript", "head", "template", "iframe"}
	out := make([]*regexp.Regexp, 0, len(names))
	for _, name := range names {
		out = append(out, regexp.MustCompile(`(?is)<`+name+`\b[^>]*>.*?</`+name+`\s*>`))
	}
	return out
}()

// 期刊页眉页脚、下载水印、版权声明等模板化噪声行。
var boilerplateLinePatterns = []*regexp.Regexp{
	regexp.MustCompile(`(?i)^(downloaded|retrieved)\s+(from|by)\b`),
	regexp.MustCompile(`(?i)^this article is protected by copyright`),
	regexp.MustCompile(`(?i)^all rights reserved`),
	regexp.MustCompile(`(?i)^copyright\s*(©|\(c\))?\s*\d{4}`),
	regexp.MustCompile(`^\s*©\s*\d{4}`),
	regexp.MustCompile(`(?i)^(terms of use|privacy policy|licen[cs]e agreement|cookie policy)\b`),
	regexp.MustCompile(`(?i)^(received|accepted|published)\s*[:：]\s*\d`),
	regexp.MustCompile(`(?i)^(https?://|www\.)`),
	regexp.MustCompile(`^doi\s*[:：]\s*10\.`),
	regexp.MustCompile(`^10\.\d{4,9}/[^\s]+$`),
	regexp.MustCompile(`(?i)^(figure|fig\.|table|scheme)\s*\d+\s*$`),
	regexp.MustCompile(`(?i)^(see|as shown in)\s+(figure|fig\.|table)\s*\d+\s*$`),
	regexp.MustCompile(`^\s*page\s+\d+(\s*(of|/)\s*\d+)?\s*$`),
	regexp.MustCompile(`^\s*-\s*\d+\s*-\s*$`),
	regexp.MustCompile(`(?i)^(supplementary|supporting information|appendix|补充材料|附图|附表)\s*$`),
}

// 参考文献段落标题，用于裁掉尾部噪声（仅当出现在文档后段时才裁剪）。
var referenceHeadingPattern = regexp.MustCompile(
	`(?i)^\s*(references|reference list|bibliography|literature cited|works cited|参考文献)\s*:?\s*$`)

// CleanDocumentText 对抽取出的正文做质量优化，移除无关内容与噪声：
//
//  1. 丢弃 script/style/head 等整块，剥离 HTML 标签，反转义 HTML 实体；
//  2. 移除控制字符与零宽/双向控制字符；
//  3. Unicode 归一化：全角转半角、弯引号/破折号/省略号/连字统一、不换行空格转空格；
//  4. 丢弃页眉页脚、下载水印、版权声明等模板化噪声行；
//  5. 裁掉文档尾部的参考文献列表（仅当位于文档后段时）；
//  6. 合并多余空行，收紧空白。
//
// 该函数不删除停用词：停用词会破坏语法结构，直接影响 embedding 语义与
// 大模型/重排模型的可读性；停用词过滤在稀疏（BM25）通道单独进行，
// 见 FilterStopwords。
func CleanDocumentText(text string) (string, CleanStats) {
	stats := CleanStats{OriginalRunes: runeCount(text)}
	if text == "" {
		return "", stats
	}

	// 1. HTML 噪声
	cleaned, tags, entities := stripHTMLNoise(text)
	stats.HTMLTagsRemoved = tags
	stats.HTMLEntitiesFixed = entities

	// 2. 控制字符与零宽字符
	cleaned, dropped := removeControlRunes(cleaned)
	stats.ControlRunesDrop = dropped

	// 3. Unicode 归一化
	cleaned, normalized := normalizeUnicodeRunes(cleaned)
	stats.UnicodeNormalized = normalized

	// 4/5. 行级噪声
	cleaned, lines := dropBoilerplateLines(cleaned)
	stats.BoilerplateLines = lines
	cleaned, trimmed := trimReferenceSection(cleaned)
	stats.ReferencesTrimmed = trimmed

	// 6. 空白收敛
	cleaned = collapseWhitespace(cleaned)
	stats.CleanedRunes = runeCount(cleaned)
	return cleaned, stats
}

// stripHTMLNoise 丢弃整块脚本/样式、剥离标签并反转义实体。
// 返回：清洗后文本、剥离的标签数、反转义的实体数。
func stripHTMLNoise(text string) (string, int, int) {
	removed := 0
	cleaned := text
	for _, block := range reHTMLBlocks {
		cleaned = block.ReplaceAllStringFunc(cleaned, func(string) string {
			removed++
			return " "
		})
	}
	cleaned = reHTMLComm.ReplaceAllStringFunc(cleaned, func(string) string {
		removed++
		return " "
	})
	cleaned = reHTMLOpen.ReplaceAllStringFunc(cleaned, func(string) string {
		removed++
		return " "
	})
	cleaned = reHTMLClose.ReplaceAllStringFunc(cleaned, func(string) string {
		removed++
		return " "
	})
	// 反转义实体（&nbsp; &amp; &#8217; ...）
	entities := len(reHTMLEnt.FindAllString(cleaned, -1))
	if entities > 0 {
		cleaned = html.UnescapeString(cleaned)
	}
	return cleaned, removed, entities
}

// removeControlRunes 删除控制字符、零宽字符与双向控制字符。
func removeControlRunes(text string) (string, int) {
	var builder strings.Builder
	builder.Grow(len(text))
	removed := 0
	for _, r := range text {
		switch {
		case r == '\n' || r == '\t':
			builder.WriteRune(r)
		case r < 0x20, r == 0x7f:
			removed++
		case r >= 0x80 && r <= 0x9f:
			removed++
		case r == 0x00ad: // soft hyphen
			removed++
		case r >= 0x200b && r <= 0x200f:
			removed++
		case r >= 0x2028 && r <= 0x202e:
			removed++
		case r >= 0x2060 && r <= 0x2064:
			removed++
		case r == 0xfeff, r >= 0xfff9 && r <= 0xfffb:
			removed++
		default:
			builder.WriteRune(r)
		}
	}
	return builder.String(), removed
}

// normalizeUnicodeRunes 做轻量 Unicode 归一化，避免引入外部依赖。
func normalizeUnicodeRunes(text string) (string, int) {
	var builder strings.Builder
	builder.Grow(len(text))
	normalized := 0
	for _, r := range text {
		switch {
		// 各种空白 -> 普通空格
		case r == 0x00a0, r >= 0x2000 && r <= 0x200a, r == 0x202f, r == 0x205f, r == 0x3000:
			builder.WriteRune(' ')
			normalized++
		// 全角字母/数字/方括号 -> 半角。
		// 刻意不转换全角标点（！＂＃…％＆＇（）＊＋，－．／：；＜＝＞？＠），
		// 因为它们在中文里是正常正文标点，且结构化摘要标记（如 "统计摘要："、
		// "第N行："）依赖全角冒号做识别，转换会导致下游解析失效。
		case r >= 0xff10 && r <= 0xff19, // ０-９
			r >= 0xff21 && r <= 0xff3a, // Ａ-Ｚ
			r >= 0xff41 && r <= 0xff5a, // ａ-ｚ
			r >= 0xff3b && r <= 0xff40, // ［＼］＾＿｀
			r >= 0xff5b && r <= 0xff5e: // ｛｜｝～
			builder.WriteRune(r - 0xfee0)
			normalized++
		// 引号
		case r == 0x2018, r == 0x2019, r == 0x201a, r == 0x201b, r == 0x2032:
			builder.WriteRune('\'')
			normalized++
		case r == 0x201c, r == 0x201d, r == 0x201e, r == 0x201f, r == 0x2033:
			builder.WriteRune('"')
			normalized++
		// 破折号/连字符
		case r == 0x2010, r == 0x2011, r == 0x2012, r == 0x2013, r == 0x2014, r == 0x2212:
			builder.WriteRune('-')
			normalized++
		// 省略号
		case r == 0x2026:
			builder.WriteString("...")
			normalized++
		// 常见连字
		case r == 0xfb00:
			builder.WriteString("ff")
			normalized++
		case r == 0xfb01:
			builder.WriteString("fi")
			normalized++
		case r == 0xfb02:
			builder.WriteString("fl")
			normalized++
		case r == 0xfb03:
			builder.WriteString("ffi")
			normalized++
		case r == 0xfb04:
			builder.WriteString("ffl")
			normalized++
		case r == 0xfb06:
			builder.WriteString("st")
			normalized++
		default:
			builder.WriteRune(r)
		}
	}
	return builder.String(), normalized
}

// dropBoilerplateLines 丢弃模板化噪声行。
func dropBoilerplateLines(text string) (string, int) {
	lines := strings.Split(strings.ReplaceAll(text, "\r\n", "\n"), "\n")
	kept := make([]string, 0, len(lines))
	removed := 0
	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		if trimmed == "" {
			kept = append(kept, "")
			continue
		}
		if isBoilerplateLine(trimmed) {
			removed++
			continue
		}
		kept = append(kept, trimmed)
	}
	return strings.Join(kept, "\n"), removed
}

func isBoilerplateLine(line string) bool {
	if runeCount(line) > 160 {
		return false
	}
	for _, pattern := range boilerplateLinePatterns {
		if pattern.MatchString(line) {
			return true
		}
	}
	return false
}

// trimReferenceSection 裁掉尾部参考文献列表。
// 需要同时满足两个条件才裁剪，避免误删正文：
//  1. 标题位于文档后半段；
//  2. 其后内容确实“像”参考文献列表（有足量含年份的长条目）。
func trimReferenceSection(text string) (string, bool) {
	lines := strings.Split(text, "\n")
	if len(lines) < 12 {
		return text, false
	}
	threshold := len(lines) / 2
	for index := len(lines) - 1; index >= threshold; index-- {
		if !referenceHeadingPattern.MatchString(strings.TrimSpace(lines[index])) {
			continue
		}
		tail := lines[index+1:]
		if runeCount(strings.Join(tail, "\n")) < 200 || !looksLikeReferenceList(tail) {
			// 该标题之后不像文献列表，继续往前找下一个候选标题
			continue
		}
		return strings.TrimSpace(strings.Join(lines[:index], "\n")), true
	}
	return text, false
}

// looksLikeReferenceList 判断标题之后的内容是否真像参考文献列表：
// 需要一定数量、且占多数的「含年份的长行」。
func looksLikeReferenceList(lines []string) bool {
	entries, nonEmpty := 0, 0
	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		if trimmed == "" {
			continue
		}
		nonEmpty++
		if isReferenceEntry(trimmed) {
			entries++
		}
	}
	if nonEmpty == 0 || entries < 3 {
		return false
	}
	return entries*100/nonEmpty >= 30
}

var reReferenceYear = regexp.MustCompile(`(?:19|20)\d{2}`)

// isReferenceEntry 判断单行是否像一条参考文献（够长且含年份）。
func isReferenceEntry(line string) bool {
	if runeCount(line) < 30 {
		return false
	}
	return reReferenceYear.MatchString(line)
}

// collapseWhitespace 合并多余空行、收紧行内空白。
func collapseWhitespace(text string) string {
	text = strings.ReplaceAll(text, "\r\n", "\n")
	text = strings.ReplaceAll(text, "\r", "\n")
	lines := strings.Split(text, "\n")
	out := make([]string, 0, len(lines))
	blankStreak := 0
	for _, line := range lines {
		// 行内多空格 -> 单空格（保留中日韩文本原样）
		fields := strings.Fields(line)
		normalized := strings.Join(fields, " ")
		if normalized == "" {
			blankStreak++
			if blankStreak > 1 {
				continue
			}
			out = append(out, "")
			continue
		}
		blankStreak = 0
		out = append(out, normalized)
	}
	return strings.TrimSpace(strings.Join(out, "\n"))
}

// IsStopword 判断 token 是否为停用词（用于稀疏/关键词通道）。
func IsStopword(token string) bool {
	if token == "" {
		return true
	}
	if _, ok := englishStopwords[strings.ToLower(token)]; ok {
		return true
	}
	if len([]rune(token)) == 1 {
		if _, ok := cjkStopwords[token]; ok {
			return true
		}
	}
	return false
}

// FilterStopwords 过滤停用词；仅用于稀疏（BM25）通道，
// 不要用于 embedding 或送入大模型/重排模型的正文。
func FilterStopwords(tokens []string) []string {
	if len(tokens) == 0 {
		return tokens
	}
	out := make([]string, 0, len(tokens))
	for _, token := range tokens {
		if IsStopword(token) {
			continue
		}
		out = append(out, token)
	}
	return out
}

var englishStopwords = map[string]struct{}{
	"a": {}, "about": {}, "above": {}, "after": {}, "again": {}, "against": {},
	"all": {}, "also": {}, "am": {}, "among": {}, "an": {}, "and": {}, "any": {},
	"are": {}, "as": {}, "at": {}, "be": {}, "because": {}, "been": {}, "before": {},
	"being": {}, "below": {}, "between": {}, "both": {}, "but": {}, "by": {},
	"can": {}, "could": {}, "did": {}, "do": {}, "does": {}, "doing": {}, "done": {},
	"during": {}, "each": {}, "either": {}, "else": {}, "etc": {}, "few": {},
	"for": {}, "from": {}, "further": {}, "had": {}, "has": {}, "have": {}, "having": {},
	"he": {}, "her": {}, "here": {}, "hers": {}, "herself": {}, "him": {}, "himself": {},
	"his": {}, "how": {}, "however": {}, "i": {}, "if": {}, "in": {}, "into": {},
	"is": {}, "it": {}, "its": {}, "itself": {}, "just": {}, "may": {}, "me": {},
	"might": {}, "more": {}, "most": {}, "much": {}, "must": {}, "my": {}, "myself": {},
	"no": {}, "nor": {}, "not": {}, "now": {}, "of": {}, "off": {}, "on": {}, "once": {},
	"only": {}, "or": {}, "other": {}, "ought": {}, "our": {}, "ours": {}, "ourselves": {},
	"out": {}, "over": {}, "own": {}, "same": {}, "shall": {}, "she": {}, "should": {},
	"so": {}, "some": {}, "such": {}, "than": {}, "that": {}, "the": {}, "their": {},
	"theirs": {}, "them": {}, "themselves": {}, "then": {}, "there": {}, "these": {},
	"they": {}, "this": {}, "those": {}, "through": {}, "to": {}, "too": {},
	"under": {}, "until": {}, "up": {}, "upon": {}, "us": {}, "very": {}, "was": {},
	"we": {}, "were": {}, "what": {}, "when": {}, "where": {}, "which": {}, "while": {},
	"who": {}, "whom": {}, "why": {}, "will": {}, "with": {}, "within": {}, "without": {},
	"would": {}, "you": {}, "your": {}, "yours": {}, "yourself": {}, "yourselves": {},
	"et": {}, "al": {}, "via": {}, "per": {}, "using": {}, "used": {}, "use": {},
}

// 中文单字停用词（CJK 通道按字切分，因此只针对单字）。
var cjkStopwords = map[string]struct{}{
	"的": {}, "了": {}, "在": {}, "是": {}, "和": {}, "与": {}, "及": {},
	"或": {}, "等": {}, "对": {}, "为": {}, "以": {}, "于": {},
	"中": {}, "上": {}, "下": {}, "而": {}, "其": {}, "之": {}, "由": {},
	"把": {}, "被": {}, "并": {}, "且": {}, "也": {}, "都": {}, "还": {},
	"就": {}, "会": {}, "能": {}, "可": {}, "要": {}, "有": {}, "这": {},
	"那": {}, "个": {}, "些": {}, "我": {}, "你": {}, "他": {}, "她": {},
	"它": {}, "们": {}, "很": {}, "更": {}, "最": {}, "从": {},
	"到": {}, "出": {}, "着": {}, "过": {}, "啊": {}, "呢": {}, "吧": {},
}

// StripHTML 仅做标签剥离（供外部单独调用）。
func StripHTML(text string) (string, int) {
	cleaned, tags, _ := stripHTMLNoise(text)
	return cleaned, tags
}

// NormalizeWhitespace 仅做空白收敛（供外部单独调用）。
func NormalizeWhitespace(text string) string {
	return collapseWhitespace(text)
}

// ContainsCJK 判断文本是否包含中日韩文字。
func ContainsCJK(text string) bool {
	for _, r := range text {
		if unicode.Is(unicode.Han, r) {
			return true
		}
	}
	return false
}
