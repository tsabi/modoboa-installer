upstream modoboa {
    server unix:%uwsgi_socket_path fail_timeout=0;
}
