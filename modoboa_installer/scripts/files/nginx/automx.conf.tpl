upstream automx {
    server unix:%uwsgi_socket_path fail_timeout=0;
}

server {
    listen 80;
    listen [::]:80;
    server_name autoconfig.%{domain};
    root /srv/automx/instance;

    access_log /var/log/nginx/autoconfig.%{domain}-access.log;
    error_log /var/log/nginx/autoconfig.%{domain}-error.log;

    location /mail/config-v1.1.xml {
        include uwsgi_params;
        uwsgi_pass automx;
    }
}
