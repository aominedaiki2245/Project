package main

import (
    "log"
    "yourproject/internal/config"
    "yourproject/internal/db"
)

func main() {
    cfg := config.Load()
    if err := db.Connect(cfg); err != nil {
        log.Fatal(err)
    }
    log.Println("DB connected")
    // Позже добавим сервер
}