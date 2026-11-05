package util

import (
	"strings"
	"testing"
)

// 句首独立代词应被替换为明确的先行词。
func TestResolveAnaphoraEnglishSentenceInitial(t *testing.T) {
	text := strings.Join([]string{
		"Autism spectrum disorder (ASD) has been linked to gut microbiota dysbiosis in children.",
		"It affects social communication and repetitive behaviours.",
		"These findings suggest a role for the microbiome.",
	}, "\n\n")

	result := ResolveAnaphora(text, "Gut microbiota in autism spectrum disorder")

	if result.Replacements != 1 {
		t.Fatalf("expected exactly 1 replacement, got %d\n%s", result.Replacements, result.Text)
	}
	if !strings.Contains(result.Text, "ASD affects social communication") {
		t.Errorf("expected 'It' to be resolved to the recent entity 'ASD':\n%s", result.Text)
	}
}

// 代词后自带中心名词（This study / These findings）时不能替换，否则会改写语义。
func TestResolveAnaphoraKeepsDeterminerPhrases(t *testing.T) {
	text := strings.Join([]string{
		"Gut microbiota dysbiosis is common in children with autism.",
		"This study investigated the association.",
		"These findings were replicated.",
	}, "\n\n")

	result := ResolveAnaphora(text, "")

	if result.Replacements != 0 {
		t.Fatalf("expected no replacement for determiner phrases, got %d\n%s", result.Replacements, result.Text)
	}
	if !strings.Contains(result.Text, "This study investigated") {
		t.Errorf("'This study' must remain untouched:\n%s", result.Text)
	}
	if !strings.Contains(result.Text, "These findings were replicated") {
		t.Errorf("'These findings' must remain untouched:\n%s", result.Text)
	}
}

// 无先行词可用时不做任何替换（宁可不改，也不能改错）。
func TestResolveAnaphoraWithoutAntecedent(t *testing.T) {
	text := "It is unclear whether the effect persists."
	result := ResolveAnaphora(text, "")
	if result.Replacements != 0 {
		t.Fatalf("expected no replacement without antecedent, got %d -> %s", result.Replacements, result.Text)
	}
}

// 标题可作为兜底先行词。
func TestResolveAnaphoraUsesTitleFallback(t *testing.T) {
	text := "It has been widely reported among children."
	result := ResolveAnaphora(text, "Autism spectrum disorder and the gut microbiome")
	if result.Replacements != 1 {
		t.Fatalf("expected title to serve as antecedent, got %d", result.Replacements)
	}
	if !strings.Contains(result.Text, "Autism spectrum disorder") {
		t.Errorf("expected title entity to be substituted:\n%s", result.Text)
	}
}

// 中文代词「它/它们」在句首时替换；限定词「该/其/此」不动。
func TestResolveAnaphoraChinesePronoun(t *testing.T) {
	text := strings.Join([]string{
		"肠道菌群失调在自闭症儿童中较为常见。",
		"它能显著影响社交行为。",
		"该研究进一步验证了这一结论。",
	}, "\n\n")

	result := ResolveAnaphora(text, "")

	if result.Replacements != 1 {
		t.Fatalf("expected exactly 1 replacement, got %d\n%s", result.Replacements, result.Text)
	}
	if !strings.Contains(result.Text, "肠道菌群失调能显著影响社交行为") {
		t.Errorf("expected '它' to be replaced by the recent Chinese entity:\n%s", result.Text)
	}
	if !strings.Contains(result.Text, "该研究进一步验证") {
		t.Errorf("determiner '该' must not be replaced:\n%s", result.Text)
	}
}

// 句子中段的代词一律不动。
func TestResolveAnaphoraIgnoresMidSentencePronouns(t *testing.T) {
	text := strings.Join([]string{
		"Gut microbiota dysbiosis is common in autism.",
		"Recent work shows that it correlates with severity scores.",
	}, "\n\n")

	result := ResolveAnaphora(text, "")
	if result.Replacements != 0 {
		t.Fatalf("mid-sentence pronoun must not be replaced, got %d -> %s", result.Replacements, result.Text)
	}
}

func TestResolveAnaphoraEmptyInput(t *testing.T) {
	result := ResolveAnaphora("", "title")
	if result.Text != "" || result.Replacements != 0 {
		t.Fatalf("unexpected result for empty input: %+v", result)
	}
}
