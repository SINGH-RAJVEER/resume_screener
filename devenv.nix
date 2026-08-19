{ config, pkgs, ... }:

{
  packages = [ pkgs.just ];

  languages.go = {
    enable = true;
    package = pkgs.go_1_26;
  };

  languages.javascript = {
    enable = true;
    bun = {
      enable = true;
      install.enable = true;
    };
  };

  services.postgres = {
    enable = true;
    package = pkgs.postgresql_18;
    listen_addresses = "127.0.0.1";
    initialDatabases = [
      {
        name = "template";
        user = "template";
        pass = "template";
      }
    ];
  };

  env = {
    DATABASE_URL = "postgresql://template:template@127.0.0.1:${toString config.processes.postgres.ports.main.value}/template?sslmode=disable";
    WEB_URL = "http://localhost:3000";
    VITE_API_URL = "http://localhost:3001";
    PORT = "3001";
    JWT_SECRET = "local-development-jwt-secret-change-me";
    JWT_TTL = "168h";
  };

  processes.api = {
    exec = "go run ./cmd/api";
    cwd = "${config.git.root}/apps/api";
    after = [ "devenv:processes:postgres" ];
    ready.http.get = {
      port = 3001;
      path = "/health";
    };
    watch = {
      paths = [ ./apps/api ];
      extensions = [ "go" "sql" "mod" "sum" ];
    };
  };

  processes.web = {
    exec = "bun run dev -- --host 127.0.0.1";
    cwd = "${config.git.root}/apps/web";
    after = [ "devenv:processes:api" ];
    ready.http.get = {
      port = 3000;
      path = "/";
    };
  };
}
