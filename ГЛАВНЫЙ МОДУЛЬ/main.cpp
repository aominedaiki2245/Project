// main.cpp
// Простой демонстрационный главный модуль для массовых опросов/тестов.
// Требует: cpp-httplib (single header) и nlohmann::json
// Сборка: g++ -std=c++17 main.cpp -o main -lpthread

#include <iostream>
#include <string>
#include <unordered_map>
#include <vector>
#include <optional>
#include <mutex>
#include <chrono>

#include "httplib.h"       // https://github.com/yhirose/cpp-httplib
#include "json.hpp"        // https://github.com/nlohmann/json

using json = nlohmann::json;
using namespace httplib;
using namespace std::chrono_literals;

// ----------------------------- Модели --------------------------------
struct User {
    std::string id;
    std::string fullName;
    std::vector<std::string> roles; // Student, Teacher, Admin
    bool blocked = false;
    std::vector<std::string> refreshTokens;
};

NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE(User, id, fullName, roles, blocked, refreshTokens)

struct Course {
    std::string id;
    std::string title;
    std::string description;
    std::string teacherId;
    bool deleted = false;
};

NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE(Course, id, title, description, teacherId, deleted)

struct Question {
    std::string id;
    std::string authorId;
    std::string title;
    std::string text;
    std::vector<std::string> options;
    int correctIndex = 0;
    int version = 1;
    bool deleted = false;
};

NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE(Question, id, authorId, title, text, options, correctIndex, version, deleted)

struct Test {
    std::string id;
    std::string courseId;
    std::string title;
    std::vector<std::string> questionIds;
    bool active = false;
    bool deleted = false;
};

NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE(Test, id, courseId, title, questionIds, active, deleted)

struct Attempt {
    std::string id;
    std::string userId;
    std::string testId;
    std::vector<std::pair<std::string,int>> q_and_versions; // questionId, version
    std::vector<int> answers; // -1 if unanswered
    bool finished = false;
    double score = 0.0;
};

NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE(Attempt, id, userId, testId, q_and_versions, answers, finished, score)

// ----------------------------- Auth client --------------------------------
// Abstraction: в реальном окружении AuthService предоставляет endpoint /verify
// который принимает access token и возвращает claims (userId, permissions, roles, exp).
struct AuthClaims {
    bool valid = false;
    std::string userId;
    std::vector<std::string> permissions;
    std::vector<std::string> roles;
    std::chrono::system_clock::time_point expiresAt;
};

class AuthClient {
    // В продакшне: endpoint, TLS, caching public key, jwks, retries, circuit-breaker, etc.
    std::string authHost;
    int authPort;
public:
    AuthClient(const std::string &host = "localhost", int port = 8081) : authHost(host), authPort(port) {}

    // Проверяет токен, возвращает claims. Здесь реализуем простую заглушку: вызываем внешний Auth Service.
    AuthClaims verifyAccessToken(const std::string &accessToken) {
        AuthClaims res;
        if (accessToken.empty()) return res;
        Client cli(authHost.c_str(), authPort);
        Headers headers = { {"Authorization", std::string("Bearer ") + accessToken} };
        if (auto r = cli.Get("/verify", headers)) {
            if (r->status == 200) {
                auto j = json::parse(r->body);
                res.valid = true;
                res.userId = j.value("userId", "");
                res.roles = j.value("roles", std::vector<std::string>{});
                res.permissions = j.value("permissions", std::vector<std::string>{});
                long long exp = j.value("exp", 0LL);
                res.expiresAt = std::chrono::system_clock::from_time_t(static_cast<time_t>(exp));
            }
        } else {
            // fallback: invalid or can't reach auth (treat as invalid)
        }
        return res;
    }
};

// ----------------------------- Репозитории (интерфейсы) -------------------------
template<typename T>
class Repo {
public:
    virtual std::optional<T> get(const std::string &id) = 0;
    virtual std::vector<T> list() = 0;
    virtual T create(const T &obj) = 0;
    virtual bool update(const std::string &id, const T &obj) = 0;
    virtual bool remove(const std::string &id) = 0;
    virtual ~Repo() = default;
};

// Простейшая in-memory реализация (для демонстрации)
template<typename T>
class InMemoryRepo : public Repo<T> {
    std::unordered_map<std::string, T> store;
    std::mutex m;
public:
    std::optional<T> get(const std::string &id) override {
        std::lock_guard lk(m);
        auto it = store.find(id);
        if (it == store.end()) return std::nullopt;
        return it->second;
    }
    std::vector<T> list() override {
        std::lock_guard lk(m);
        std::vector<T> res;
        res.reserve(store.size());
        for (auto &p: store) res.push_back(p.second);
        return res;
    }
    T create(const T &obj) override {
        std::lock_guard lk(m);
        store[obj.id] = obj;
        return obj;
    }
    bool update(const std::string &id, const T &obj) override {
        std::lock_guard lk(m);
        auto it = store.find(id);
        if (it == store.end()) return false;
        it->second = obj;
        return true;
    }
    bool remove(const std::string &id) override {
        std::lock_guard lk(m);
        auto it = store.find(id);
        if (it == store.end()) return false;
        // soft delete depends on T; here just erase
        store.erase(it);
        return true;
    }
};

// ----------------------------- Utility --------------------------------
std::string make_id(const std::string &prefix) {
    static std::atomic_uint64_t ctr{1};
    auto v = ctr++;
    return prefix + std::to_string(v);
}

bool contains(const std::vector<std::string>& v, const std::string &x) {
    for (auto &s: v) if (s==x) return true;
    return false;
}

// Проверка прав: сначала проверяем явную пермишн в JWT, потом – правило по умолчанию (например, "это мой ресурс")
bool checkPermission(const AuthClaims &claims, const std::string &requiredPermission,
                     const std::string &resourceOwnerId, const std::string &requesterId) {
    if (!claims.valid) return false;
    // admin shortcut
    if (contains(claims.roles, "Admin")) return true;
    if (!requiredPermission.empty() && contains(claims.permissions, requiredPermission)) return true;
    // default owner rules: if resource owner == requester, allow
    if (!requiredPermission.empty()) {
        // some permissions are allowed by default for owners (example)
        if (resourceOwnerId.size() > 0 && resourceOwnerId == requesterId) return true;
    }
    return false;
}

// ----------------------------- Main: сервис и маршруты ----------------------------
int main() {
    // Репозитории (в замену подключение к БД)
    auto usersRepo = std::make_shared<InMemoryRepo<User>>();
    auto coursesRepo = std::make_shared<InMemoryRepo<Course>>();
    auto questionsRepo = std::make_shared<InMemoryRepo<Question>>();
    auto testsRepo = std::make_shared<InMemoryRepo<Test>>();
    auto attemptsRepo = std::make_shared<InMemoryRepo<Attempt>>();

    // добавим тестового админа
    User admin{"u1", "Administrator", {"Admin"}, false, {}};
    usersRepo->create(admin);

    AuthClient authClient("localhost", 8081); // адаптируйте host:port

    Server srv;

    // Middleware: извлечь токен, вернуть claims
    auto extractClaims = [&](const Request &req)->AuthClaims {
        auto it = req.headers.find("Authorization");
        if (it == req.headers.end()) return AuthClaims{};
        std::string header = it->second;
        const std::string bearer = "Bearer ";
        if (header.rfind(bearer,0) == 0) {
            std::string token = header.substr(bearer.size());
            return authClient.verifyAccessToken(token);
        }
        return AuthClaims{};
    };

    // ---------- Users ----------
    srv.Get(R"(/users/?$)", [&](const Request& req, Response& res){
        auto claims = extractClaims(req);
        if (!claims.valid) { res.status = 401; return; }
        // проверка permission: user:list:read
        if (!checkPermission(claims, "user:list:read", "", claims.userId)) { res.status = 403; return; }
        auto list = usersRepo->list();
        json out = list;
        res.set_content(out.dump(), "application/json");
    });

    srv.Get(R"(/users/([A-Za-z0-9_:-]+))", [&](const Request& req, Response& res){
        auto claims = extractClaims(req);
        if (!claims.valid) { res.status = 401; return; }
        std::string id = req.matches[1];
        auto maybe = usersRepo->get(id);
        if (!maybe) { res.status = 404; return; }
        // default: anyone can view own fullName; others require permission user:data:read or user:fullName:read
        if (!checkPermission(claims, "user:data:read", id, claims.userId)) {
            // maybe allowed to see basic fullName if owner
            if (claims.userId != id && !checkPermission(claims, "user:fullName:read", id, claims.userId)) {
                res.status = 403; return;
            }
        }
        json out = *maybe;
        res.set_content(out.dump(), "application/json");
    });

    srv.Put(R"(/users/([A-Za-z0-9_:-]+))", [&](const Request& req, Response& res){
        auto claims = extractClaims(req);
        if (!claims.valid) { res.status = 401; return; }
        std::string id = req.matches[1];
        auto maybe = usersRepo->get(id);
        if (!maybe) { res.status = 404; return; }
        // изменение ФИО: permission user:fullName:write or owner
        if (!checkPermission(claims, "user:fullName:write", id, claims.userId)) { res.status = 403; return; }
        json body = json::parse(req.body);
        User u = *maybe;
        if (body.contains("fullName")) u.fullName = body["fullName"].get<std::string>();
        usersRepo->update(id, u);
        res.status = 200;
    });

    // ---------- Courses ----------
    srv.Get(R"(/courses/?$)", [&](const Request& req, Response& res){
        // anyone can list courses by default (+public)
        auto list = coursesRepo->list();
        json out = list;
        res.set_content(out.dump(), "application/json");
    });

    srv.Post(R"(/courses/?$)", [&](const Request& req, Response& res){
        auto claims = extractClaims(req);
        if (!claims.valid) { res.status = 401; return; }
        // only users with course:add or Admin can create a course
        if (!checkPermission(claims, "course:add", "", claims.userId)) { res.status = 403; return; }
        json body = json::parse(req.body);
        Course c;
        c.id = make_id("c");
        c.title = body.value("title", std::string("untitled"));
        c.description = body.value("description", std::string{});
        c.teacherId = body.value("teacherId", claims.userId);
        coursesRepo->create(c);
        res.status = 201;
        res.set_content(json{{"id", c.id}}.dump(), "application/json");
    });

    // ---------- Questions ----------
    srv.Post(R"(/questions/?$)", [&](const Request& req, Response& res){
        auto claims = extractClaims(req);
        if (!claims.valid) { res.status = 401; return; }
        // require quest:create permission
        if (!checkPermission(claims, "quest:create", "", claims.userId)) { res.status = 403; return; }
        json body = json::parse(req.body);
        Question q;
        q.id = make_id("q");
        q.authorId = claims.userId;
        q.title = body.value("title", std::string{"untitled"});
        q.text = body.value("text", std::string{});
        q.options = body.value("options", std::vector<std::string>{});
        q.correctIndex = body.value("correctIndex", 0);
        questionsRepo->create(q);
        res.status = 201;
        res.set_content(json{{"id", q.id}}.dump(), "application/json");
    });

    srv.Get(R"(/questions/([A-Za-z0-9_:-]+))", [&](const Request& req, Response& res){
        auto claims = extractClaims(req);
        if (!claims.valid) { res.status = 401; return; }
        std::string id = req.matches[1];
        auto maybe = questionsRepo->get(id);
        if (!maybe) { res.status = 404; return; }
        const auto &q = *maybe;
        // access: owner can read, or student who has an attempt referencing question, or perm quest:read
        if (!checkPermission(claims, "quest:read", q.authorId, claims.userId)) {
            res.status = 403; return;
        }
        res.set_content(json(q).dump(), "application/json");
    });

    // ---------- Tests ----------
    srv.Post(R"(/tests/?$)", [&](const Request& req, Response& res){
        auto claims = extractClaims(req);
        if (!claims.valid) { res.status = 401; return; }
        // require course:test:add or course:add; here we require test:create
        if (!checkPermission(claims, "test:create", "", claims.userId)) { res.status = 403; return; }
        json body = json::parse(req.body);
        Test t;
        t.id = make_id("t");
        t.courseId = body.value("courseId", std::string{});
        t.title = body.value("title", std::string{"untitled test"});
        testsRepo->create(t);
        res.status = 201;
        res.set_content(json{{"id", t.id}}.dump(), "application/json");
    });

    srv.Get(R"(/tests/([A-Za-z0-9_:-]+))", [&](const Request& req, Response& res){
        auto claims = extractClaims(req);
        std::string id = req.matches[1];
        auto maybe = testsRepo->get(id);
        if (!maybe) { res.status = 404; return; }
        if (!claims.valid) { res.status = 401; return; }
        // require course:test:read or default rules (e.g. student enrolled)
        if (!checkPermission(claims, "course:test:read", maybe->courseId, claims.userId)) { res.status = 403; return; }
        res.set_content(json(*maybe).dump(), "application/json");
    });

    // ---------- Attempts / Answers ----------
    srv.Post(R"(/tests/([A-Za-z0-9_:-]+)/attempts/?$)", [&](const Request& req, Response& res){
        auto claims = extractClaims(req);
        if (!claims.valid) { res.status = 401; return; }
        std::string testId = req.matches[1];
        auto maybeTest = testsRepo->get(testId);
        if (!maybeTest) { res.status = 404; return; }
        if (!maybeTest->active) { res.status = 400; res.set_content("Test not active"); return; }
        // default: only students can create attempt; require test-taking (no permission name)
        // check if user already has attempt: (simplified) not implemented
        Attempt a;
        a.id = make_id("att");
        a.userId = claims.userId;
        a.testId = testId;
        // build questions versions
        for (auto &qid: maybeTest->questionIds) {
            // select last version (simplified: version stored in question struct)
            auto q = questionsRepo->get(qid);
            if (q) {
                a.q_and_versions.emplace_back(qid, q->version);
                a.answers.push_back(-1);
            }
        }
        attemptsRepo->create(a);
        res.status = 201;
        res.set_content(json{{"id", a.id}}.dump(), "application/json");
    });

    srv.Put(R"(/attempts/([A-Za-z0-9_:-]+)/answer/?$)", [&](const Request& req, Response& res){
        auto claims = extractClaims(req);
        if (!claims.valid) { res.status = 401; return; }
        std::string attemptId = req.matches[1];
        auto maybeAtt = attemptsRepo->get(attemptId);
        if (!maybeAtt) { res.status = 404; return; }
        if (maybeAtt->userId != claims.userId) { res.status = 403; return; }
        if (maybeAtt->finished) { res.status = 400; res.set_content("Attempt finished"); return; }
        json body = json::parse(req.body);
        int qIndex = body.value("qIndex", -1);
        int choice = body.value("choice", -1);
        if (qIndex < 0 || qIndex >= (int)maybeAtt->answers.size()) { res.status = 400; return; }
        maybeAtt->answers[qIndex] = choice;
        attemptsRepo->update(attemptId, *maybeAtt);
        res.status = 200;
    });

    srv.Post(R"(/attempts/([A-Za-z0-9_:-]+)/finish/?$)", [&](const Request& req, Response& res){
        auto claims = extractClaims(req);
        if (!claims.valid) { res.status = 401; return; }
        std::string attemptId = req.matches[1];
        auto maybeAtt = attemptsRepo->get(attemptId);
        if (!maybeAtt) { res.status = 404; return; }
        if (maybeAtt->userId != claims.userId) { res.status = 403; return; }
        if (maybeAtt->finished) { res.status = 400; return; }
        // compute score (simple)
        double correct = 0;
        for (size_t i=0;i<maybeAtt->q_and_versions.size();++i) {
            auto qid = maybeAtt->q_and_versions[i].first;
            auto q = questionsRepo->get(qid);
            if (q) {
                if (maybeAtt->answers[i] == q->correctIndex) correct += 1.0;
            }
        }
        maybeAtt->finished = true;
        maybeAtt->score = (maybeAtt->q_and_versions.size() ? (correct / maybeAtt->q_and_versions.size()) * 100.0 : 0.0);
        attemptsRepo->update(attemptId, *maybeAtt);
        res.set_content(json{{"score", maybeAtt->score}}.dump(), "application/json");
    });

    // ---------- Notifications, health, etc ----------
    srv.Get(R"(/health/?$)", [&](const Request& req, Response& res){
        res.set_content("OK", "text/plain");
    });

    std::cout << "Main module started on port 8080\n";
    srv.listen("0.0.0.0", 8080);
    return 0;
}
