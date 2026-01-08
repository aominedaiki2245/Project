package notify

import (
	"bytes"
	"encoding/json"
	"net/http"
)

type TelegramSender struct {
	BotToken string
}

func (t *TelegramSender) SendMessage(chatID int64, text string) error {
	url := "https://api.telegram.org/bot" + t.BotToken + "/sendMessage"

	body, err := json.Marshal(map[string]interface{}{
		"chat_id": chatID,
		"text":    text,
	})
	if err != nil {
		return err
	}

	resp, err := http.Post(url, "application/json", bytes.NewBuffer(body))
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return err
	}
	return nil
}
