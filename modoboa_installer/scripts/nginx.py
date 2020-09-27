# -*- coding: utf-8 -*-
"""Nginx related tools."""

try:
    import configparser
except ImportError:
    import ConfigParser as configparser
import os

from .. import package
from .. import system
from .. import utils

from . import base
from .uwsgi import Uwsgi


class Nginx(base.Installer):
    """Nginx installer."""

    appname = "nginx"
    packages = {"deb": ["nginx", "ssl-cert"], "rpm": ["nginx"]}

    def get_template_context(self, app):
        """Additionnal variables."""
        context = super(Nginx, self).get_template_context()
        context.update(
            {
                "app_instance_path": (self.config.get(app, "instance_path")),
                "uwsgi_socket_path": (
                    Uwsgi(self.config, self.upgrade).get_socket_path(app)
                ),
            }
        )
        return context

    def _setup_config(
        self,
        app,
        hostname=None,
        tls_cert_file=None,
        tls_key_file=None,
        extra_config=None,
        config_file_name=None,
    ):
        """Custom app configuration."""
        if not hostname:
            hostname = self.config.get("general", "hostname_smtp")
        if not tls_cert_file:
            tls_cert_file = self.config.get("general", "tls_cert_file_smtp")
        if not tls_key_file:
            tls_key_file = self.config.get("general", "tls_key_file_smtp")
        if not config_file_name:
            config_file_name = hostname
        try:
            context = self.get_template_context(app)
        except configparser.NoSectionError:
            # some general template dont have section in the config file,
            # modoboa section will do it for them
            context = self.get_template_context("modoboa")
        context.update(
            {
                "hostname": hostname,
                "tls_cert_file": tls_cert_file,
                "tls_key_file": tls_key_file,
                "extra_config": extra_config,
            }
        )
        src = self.get_file_path("{}.conf.tpl".format(app))
        if package.backend.FORMAT == "deb":
            dst = os.path.join(
                self.config_dir, "sites-available", "{}.conf".format(config_file_name)
            )
            utils.copy_from_template(src, dst, context)
            link = os.path.join(self.config_dir, "sites-enabled", os.path.basename(dst))
            if os.path.exists(link):
                return
            os.symlink(dst, link)
            try:
                group = self.config.get(app, "user")
            except configparser.NoSectionError:
                # some general template dont have section in the config file,
                # modoboa section will do it for them
                group = self.config.get("modoboa", "user")
            user = "www-data"
        else:
            dst = os.path.join(
                self.config_dir, "conf.d", "{}.conf".format(config_file_name)
            )
            utils.copy_from_template(src, dst, context)
            group = "uwsgi"
            user = "nginx"
        system.add_user_to_group(user, group)

    def post_run(self):
        """Additionnal tasks."""
        # proxy services
        self._setup_config("proxy_services", config_file_name="000_proxy_services")

        extra_modoboa_config = ""
        if self.config.getboolean("automx", "enabled"):
            hostname = "autoconfig.{}".format(self.config.get("general", "domain"))
            self._setup_config("automx", hostname=hostname)
            extra_modoboa_config += """
    location ~* ^/autodiscover/autodiscover.xml {
        include uwsgi_params;
        uwsgi_pass automx;
    }
    location /mobileconfig {
        include uwsgi_params;
        uwsgi_pass automx;
    }
"""
        if self.config.get("radicale", "enabled"):
            extra_modoboa_config += """
    location /radicale/ {
        proxy_pass http://localhost:5232/; # The / is important!
        proxy_set_header X-Script-Name /radicale;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_pass_header Authorization;
    }
"""
        # SMTP server
        self._setup_config("modoboa", extra_config=extra_modoboa_config)
        # IMAP server, if address is different than SMTP
        if self.config.get("general", "hostname_smtp") != self.config.get(
            "general", "hostname_imap"
        ):
            self._setup_config(
                "modoboa",
                hostname=self.config.get("general", "hostname_imap"),
                tls_cert_file=self.config.get("general", "tls_cert_file_imap"),
                tls_key_file=self.config.get("general", "tls_key_file_imap"),
                extra_config=extra_modoboa_config,
            )

        if not os.path.exists("{}/dhparam.pem".format(self.config_dir)):
            cmd = "openssl dhparam -dsaparam -out dhparam.pem 4096"
            utils.exec_cmd(cmd, cwd=self.config_dir)
