package mail

import (
	"crypto/tls"
	"fmt"
	"net"
	"net/smtp"
	"os"
	"strconv"
	"strings"
)

type Message struct {
	To       []string
	Subject  string
	TextBody string
	ReplyTo  string
}

type SMTPConfig struct {
	Host    string
	Port    int
	User    string
	Pass    string
	From    string
	ReplyTo string
}

type Sender interface {
	Send(msg Message) error
}

type SMTPSender struct {
	cfg SMTPConfig
}

func NewSMTPSender(cfg SMTPConfig) (*SMTPSender, error) {
	cfg.Host = strings.TrimSpace(cfg.Host)
	if cfg.Host == "" {
		return nil, fmt.Errorf("smtp host required")
	}
	if cfg.Port == 0 {
		cfg.Port = 587
	}
	if strings.TrimSpace(cfg.User) == "" || strings.TrimSpace(cfg.Pass) == "" {
		return nil, fmt.Errorf("smtp user and pass required")
	}
	if strings.TrimSpace(cfg.From) == "" {
		return nil, fmt.Errorf("smtp from required")
	}
	return &SMTPSender{cfg: cfg}, nil
}

func NewSMTPSenderFromEnv() (*SMTPSender, error) {
	port := 587
	if raw := strings.TrimSpace(os.Getenv("SMTP_PORT")); raw != "" {
		if parsed, err := strconv.Atoi(raw); err == nil {
			port = parsed
		}
	}
	cfg := SMTPConfig{
		Host:    envOrDefault("SMTP_HOST", "smtp.gmail.com"),
		Port:    port,
		User:    os.Getenv("SMTP_USER"),
		Pass:    os.Getenv("SMTP_PASS"),
		From:    os.Getenv("SMTP_FROM"),
		ReplyTo: os.Getenv("SMTP_REPLY_TO"),
	}
	if strings.TrimSpace(cfg.ReplyTo) == "" {
		cfg.ReplyTo = cfg.From
	}
	return NewSMTPSender(cfg)
}

func (s *SMTPSender) Send(msg Message) error {
	if s == nil {
		return fmt.Errorf("smtp sender not configured")
	}
	if len(msg.To) == 0 {
		return fmt.Errorf("missing recipients")
	}
	if strings.TrimSpace(msg.Subject) == "" {
		return fmt.Errorf("missing subject")
	}

	addr := fmt.Sprintf("%s:%d", s.cfg.Host, s.cfg.Port)
	conn, err := net.Dial("tcp", addr)
	if err != nil {
		return fmt.Errorf("smtp dial: %w", err)
	}
	defer conn.Close()

	client, err := smtp.NewClient(conn, s.cfg.Host)
	if err != nil {
		return fmt.Errorf("smtp client: %w", err)
	}
	defer client.Close()

	if ok, _ := client.Extension("STARTTLS"); ok {
		if err := client.StartTLS(&tls.Config{ServerName: s.cfg.Host}); err != nil {
			return fmt.Errorf("smtp starttls: %w", err)
		}
	}

	auth := smtp.PlainAuth("", s.cfg.User, s.cfg.Pass, s.cfg.Host)
	if err := client.Auth(auth); err != nil {
		return fmt.Errorf("smtp auth: %w", err)
	}

	if err := client.Mail(s.cfg.From); err != nil {
		return fmt.Errorf("smtp mail from: %w", err)
	}
	for _, rcpt := range msg.To {
		rcpt = strings.TrimSpace(rcpt)
		if rcpt == "" {
			continue
		}
		if err := client.Rcpt(rcpt); err != nil {
			return fmt.Errorf("smtp rcpt %s: %w", rcpt, err)
		}
	}

	w, err := client.Data()
	if err != nil {
		return fmt.Errorf("smtp data: %w", err)
	}
	if _, err := w.Write([]byte(renderMessage(s.cfg, msg))); err != nil {
		return fmt.Errorf("smtp write: %w", err)
	}
	if err := w.Close(); err != nil {
		return fmt.Errorf("smtp close: %w", err)
	}

	if err := client.Quit(); err != nil {
		return fmt.Errorf("smtp quit: %w", err)
	}
	return nil
}

func renderMessage(cfg SMTPConfig, msg Message) string {
	toLine := strings.Join(msg.To, ", ")
	replyTo := strings.TrimSpace(msg.ReplyTo)
	if replyTo == "" {
		replyTo = cfg.ReplyTo
	}
	if replyTo == "" {
		replyTo = cfg.From
	}

	headers := []string{
		fmt.Sprintf("From: %s", cfg.From),
		fmt.Sprintf("To: %s", toLine),
		fmt.Sprintf("Subject: %s", sanitizeHeader(msg.Subject)),
		"MIME-Version: 1.0",
		"Content-Type: text/plain; charset=\"utf-8\"",
	}
	if replyTo != "" {
		headers = append(headers, fmt.Sprintf("Reply-To: %s", replyTo))
	}

	return strings.Join(headers, "\r\n") + "\r\n\r\n" + msg.TextBody + "\r\n"
}

func sanitizeHeader(v string) string {
	v = strings.ReplaceAll(v, "\r", "")
	v = strings.ReplaceAll(v, "\n", " ")
	return v
}

func envOrDefault(key, def string) string {
	v := strings.TrimSpace(os.Getenv(key))
	if v == "" {
		return def
	}
	return v
}
