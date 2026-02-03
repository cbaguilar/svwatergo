package metadata

import (
	"fmt"
	"strconv"
	"strings"
	"unicode"
)

type tokenType int

const (
	tokNumber tokenType = iota
	tokIdent
	tokOp
	tokLParen
	tokRParen
)

type token struct {
	typ tokenType
	val string
}

func tokenize(expr string) ([]token, error) {
	var out []token
	s := strings.TrimSpace(expr)
	i := 0
	for i < len(s) {
		ch := s[i]
		switch {
		case unicode.IsSpace(rune(ch)):
			i++
		case ch == '(':
			out = append(out, token{typ: tokLParen, val: "("})
			i++
		case ch == ')':
			out = append(out, token{typ: tokRParen, val: ")"})
			i++
		case ch == '+' || ch == '-' || ch == '*' || ch == '/':
			out = append(out, token{typ: tokOp, val: string(ch)})
			i++
		case unicode.IsDigit(rune(ch)) || ch == '.':
			start := i
			i++
			for i < len(s) {
				c := s[i]
				if unicode.IsDigit(rune(c)) || c == '.' || c == 'e' || c == 'E' || c == '-' || c == '+' {
					i++
					continue
				}
				break
			}
			out = append(out, token{typ: tokNumber, val: s[start:i]})
		case unicode.IsLetter(rune(ch)) || ch == '_':
			start := i
			i++
			for i < len(s) {
				c := s[i]
				if unicode.IsLetter(rune(c)) || unicode.IsDigit(rune(c)) || c == '_' {
					i++
					continue
				}
				break
			}
			out = append(out, token{typ: tokIdent, val: s[start:i]})
		default:
			return nil, fmt.Errorf("invalid character %q in expr", ch)
		}
	}
	return out, nil
}

func precedence(op string) int {
	switch op {
	case "+", "-":
		return 1
	case "*", "/":
		return 2
	default:
		return 0
	}
}

func toRPN(tokens []token) ([]token, error) {
	var out []token
	var stack []token

	// handle unary minus by injecting a leading 0
	prevWasOp := true
	for _, t := range tokens {
		if t.typ == tokOp && t.val == "-" && prevWasOp {
			out = append(out, token{typ: tokNumber, val: "0"})
		}

		switch t.typ {
		case tokNumber, tokIdent:
			out = append(out, t)
			prevWasOp = false
		case tokOp:
			for len(stack) > 0 {
				top := stack[len(stack)-1]
				if top.typ == tokOp && precedence(top.val) >= precedence(t.val) {
					out = append(out, top)
					stack = stack[:len(stack)-1]
					continue
				}
				break
			}
			stack = append(stack, t)
			prevWasOp = true
		case tokLParen:
			stack = append(stack, t)
			prevWasOp = true
		case tokRParen:
			found := false
			for len(stack) > 0 {
				top := stack[len(stack)-1]
				stack = stack[:len(stack)-1]
				if top.typ == tokLParen {
					found = true
					break
				}
				out = append(out, top)
			}
			if !found {
				return nil, fmt.Errorf("mismatched parentheses")
			}
			prevWasOp = false
		}
	}

	for len(stack) > 0 {
		top := stack[len(stack)-1]
		stack = stack[:len(stack)-1]
		if top.typ == tokLParen || top.typ == tokRParen {
			return nil, fmt.Errorf("mismatched parentheses")
		}
		out = append(out, top)
	}
	return out, nil
}

func EvalExpr(expr string, vars map[string]float64) (float64, error) {
	toks, err := tokenize(expr)
	if err != nil {
		return 0, err
	}
	rpn, err := toRPN(toks)
	if err != nil {
		return 0, err
	}

	var stack []float64
	for _, t := range rpn {
		switch t.typ {
		case tokNumber:
			v, err := strconv.ParseFloat(t.val, 64)
			if err != nil {
				return 0, fmt.Errorf("invalid number %q", t.val)
			}
			stack = append(stack, v)
		case tokIdent:
			v, ok := vars[t.val]
			if !ok {
				return 0, fmt.Errorf("unknown variable %q", t.val)
			}
			stack = append(stack, v)
		case tokOp:
			if len(stack) < 2 {
				return 0, fmt.Errorf("invalid expression")
			}
			b := stack[len(stack)-1]
			a := stack[len(stack)-2]
			stack = stack[:len(stack)-2]
			switch t.val {
			case "+":
				stack = append(stack, a+b)
			case "-":
				stack = append(stack, a-b)
			case "*":
				stack = append(stack, a*b)
			case "/":
				stack = append(stack, a/b)
			default:
				return 0, fmt.Errorf("unsupported op %q", t.val)
			}
		default:
			return 0, fmt.Errorf("unexpected token in rpn")
		}
	}

	if len(stack) != 1 {
		return 0, fmt.Errorf("invalid expression")
	}
	return stack[0], nil
}
