{ pkgs, lib, config, ... }:

let
	# Ports follow docker-compose defaults. Override per invocation when they
	# collide with other local services, e.g.:
	#   SKILLSIGNAL_API_PORT=8010 SKILLSIGNAL_WEB_PORT=3010 devenv up
	apiPort =
		let value = builtins.getEnv "SKILLSIGNAL_API_PORT";
		in if value == "" then "8000" else value;
	webPort =
		let value = builtins.getEnv "SKILLSIGNAL_WEB_PORT";
		in if value == "" then "3000" else value;

	# DATABASE_URL is assembled at process start from PGHOST/PGPORT because
	# devenv resolves the postgres port per invocation when 5432 is busy. The
	# +asyncpg scheme is required by the worker and accepted by the API.
	processDbUrl =
		"export DATABASE_URL=\"postgresql+asyncpg://postgres:password@\$PGHOST:\$PGPORT/skillsignal\"";
in
{
	dotenv.disableHint = true;

	languages.javascript = {
		enable = true;
		bun.enable = true;
		bun.install.enable = true;
	};

	# Python is managed by uv (per-project .venv in apps/api and apps/worker);
	# providing the interpreter on PATH keeps uv from downloading its own.
	# libstdc++ is needed by manylinux wheels such as greenlet on NixOS.
	packages = [
		pkgs.python314
		pkgs.uv
		pkgs.stdenv.cc.cc.lib
	];

	services.postgres = {
		enable = true;
		package = pkgs.postgresql_18;
		listen_addresses = "127.0.0.1";
		initialDatabases = [
			{
				name = "skillsignal";
				user = "postgres";
				pass = "password";
			}
		];
	};

	env = {
		JWT_SECRET = "devenv-local-jwt-secret-not-for-production";
		STORAGE_ROOT = "${config.devenv.root}/.local-storage";
		WEB_URL = "http://localhost:${webPort}";
		VITE_API_URL = "http://localhost:${apiPort}";
		LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [ pkgs.stdenv.cc.cc.lib ];
	};

	processes.api = {
		exec = lib.concatStringsSep "\n" [
			processDbUrl
			# Same boot sequence as apps/api/Dockerfile: migrate, then serve.
			''.venv/bin/python migrate.py upgrade head && exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port ${apiPort} --reload''
		];
		cwd = "${config.devenv.root}/apps/api";
		after = [ "devenv:processes:postgres@ready" ];
		# Migrations run before uvicorn binds; allow a few minutes of boot time.
		ready.http.get.port = lib.toInt apiPort;
		ready.http.get.path = "/health";
		ready.period = 3;
		ready.probe_timeout = 2;
		ready.failure_threshold = 60;
	};

	processes.worker = {
		exec = lib.concatStringsSep "\n" [
			processDbUrl
			"exec .venv/bin/python -m worker.main"
		];
		cwd = "${config.devenv.root}/apps/worker";
		# Wait for the API so migrations have created the job tables.
		after = [ "devenv:processes:api@ready" ];
	};

	processes.web = {
		exec = "exec bun run dev --strictPort --port ${webPort}";
		cwd = "${config.devenv.root}/apps/web";
		ready.http.get.port = lib.toInt webPort;
		ready.http.get.path = "/";
	};

	enterShell = ''
		uv sync --project "$DEVENV_ROOT/apps/api"
		uv sync --project "$DEVENV_ROOT/apps/worker"

		export DATABASE_URL="postgresql+asyncpg://postgres:password@$PGHOST:$PGPORT/skillsignal"

		# Local secrets (.env, gitignored) feed optional integrations such as
		# OpenRouter and Razorpay. Existing variables win so the preview keeps
		# targeting the devenv-managed Postgres.
		if [ -f "$DEVENV_ROOT/.env" ]; then
			while IFS='=' read -r key value || [ -n "$key" ]; do
				case "$key" in ""|"#"*) continue ;; esac
				if [ -z "''${!key+x}" ]; then
					export "''${key}=''${value%$'\r'}"
				fi
			done < "$DEVENV_ROOT/.env"
		fi
	'';

	infoSections."developer preview" = [
		"web      http://localhost:${webPort}"
		"api      http://localhost:${apiPort}/health"
		"postgres psql --dbname skillsignal --username postgres (uses $PGHOST/$PGPORT)"
	];
}
