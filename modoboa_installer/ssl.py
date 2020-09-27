# -*- coding: utf-8 -*-
"""SSL tools."""

import os
import sys

from . import package
from . import utils


class CertificateBackend(object):
    """Base class."""

    def __init__(self, config):
        """Set path to certificates."""
        self.config = config

    def overwrite_existing_certificate(self):
        """Check if certificate already exists."""
        if os.path.exists(self.config.get("general", "tls_key_file_smtp")):
            if not self.config.getboolean("general", "force"):
                answer = utils.user_input(
                    "Overwrite the existing SSL certificate? (y/N) "
                )
                if not answer.lower().startswith("y"):
                    return False
        return True


class SelfSignedCertificate(CertificateBackend):
    """Create a self signed certificate."""

    def __init__(self, *args, **kwargs):
        """Sanity checks."""
        super(SelfSignedCertificate, self).__init__(*args, **kwargs)
        if self.config.has_option("general", "tls_key_file_smtp"):
            # Compatibility
            return
        for base_dir in ["/etc/pki/tls", "/etc/ssl"]:
            if not os.path.exists(base_dir):
                continue

            # SMTP hostname
            self.config.set(
                "general",
                "tls_key_file_smtp",
                "{}/private/%(hostname_smtp)s.key".format(base_dir),
            )
            self.config.set(
                "general",
                "tls_cert_file_smtp",
                "{}/certs/%(hostname_smtp)s.cert".format(base_dir),
            )
            # IMAP hostname
            self.config.set(
                "general",
                "tls_key_file_imap",
                "{}/private/%(hostname_imap)s.key".format(base_dir),
            )
            self.config.set(
                "general",
                "tls_cert_file_imap",
                "{}/certs/%(hostname_imap)s.cert".format(base_dir),
            )
            return
        raise RuntimeError("Cannot find a directory to store certificate")

    def generate_cert(self):
        """Create a certificate."""
        if not self.overwrite_existing_certificate():
            return
        utils.printcolor("Generating new self-signed certificate", utils.YELLOW)
        utils.exec_cmd(
            "openssl req -new -newkey rsa:4096 -days 365 -nodes -x509 "
            "-subj '/CN={}' -keyout {} -out {}".format(
                self.config.get("general", "hostname_smtp"),
                self.config.get("general", "tls_key_file_smtp"),
                self.config.get("general", "tls_cert_file_smtp"),
            )
        )
        if self.config.get("general", "hostname_smtp") != self.config.get(
            "general", "hostname_imap"
        ):
            utils.exec_cmd(
                "openssl req -new -newkey rsa:4096 -days 365 -nodes -x509 "
                "-subj '/CN={}' -keyout {} -out {}".format(
                    self.config.get("general", "hostname_imap"),
                    self.config.get("general", "tls_key_file_imap"),
                    self.config.get("general", "tls_cert_file_imap"),
                )
            )


class LetsEncryptCertificate(CertificateBackend):
    """Create a certificate using letsencrypt."""

    def __init__(self, *args, **kwargs):
        """Update config."""
        super(LetsEncryptCertificate, self).__init__(*args, **kwargs)
        # SMTP hostname
        self.hostname_smtp = self.config.get("general", "hostname_smtp")
        self.config.set(
            "general",
            "tls_cert_file_smtp",
            ("/etc/letsencrypt/live/{}/fullchain.pem".format(self.hostname_smtp)),
        )
        self.config.set(
            "general",
            "tls_key_file_smtp",
            ("/etc/letsencrypt/live/{}/privkey.pem".format(self.hostname_smtp)),
        )
        # IMAP hostname
        self.hostname_imap = self.config.get("general", "hostname_imap")
        self.config.set(
            "general",
            "tls_cert_file_imap",
            ("/etc/letsencrypt/live/{}/fullchain.pem".format(self.hostname_imap)),
        )
        self.config.set(
            "general",
            "tls_key_file_imap",
            ("/etc/letsencrypt/live/{}/privkey.pem".format(self.hostname_imap)),
        )

    def install_certbot(self):
        """Install certbot script to generate cert."""
        name, version, _id = utils.dist_info()
        if name == "Ubuntu":
            package.backend.update()
            package.backend.install("software-properties-common")
            utils.exec_cmd("add-apt-repository -y universe")
            if version == "18.04":
                utils.exec_cmd("add-apt-repository -y ppa:certbot/certbot")
            package.backend.update()
            package.backend.install("certbot")
        elif name == "Debian":
            package.backend.update()
            package.backend.install("certbot")
        elif "CentOS" in name:
            package.backend.install("certbot")
        else:
            utils.printcolor("Failed to install certbot, aborting.", utils.RED)
            sys.exit(1)

    def generate_cert(self):
        """Create a certificate."""
        utils.printcolor("Generating new certificate using letsencrypt", utils.YELLOW)
        self.install_certbot()
        # smtp certificate
        utils.exec_cmd(
            "certbot certonly -n --standalone -d {} -m {} --agree-tos".format(
                self.hostname_smtp, self.config.get("letsencrypt", "email")
            )
        )
        # rewrite config
        cfg_file = "/etc/letsencrypt/renewal/{}.conf".format(self.hostname_smtp)
        pattern = "s/authenticator = standalone/authenticator = nginx/"
        utils.exec_cmd("perl -pi -e '{}' {}".format(pattern, cfg_file))
        # imap certificate
        if self.hostname_smtp != self.hostname_imap:
            utils.exec_cmd(
                "certbot certonly -n --standalone -d {} -m {} --agree-tos".format(
                    self.hostname_imap, self.config.get("letsencrypt", "email")
                )
            )
            # rewrite config
            cfg_file = "/etc/letsencrypt/renewal/{}.conf".format(self.hostname_imap)
            pattern = "s/authenticator = standalone/authenticator = nginx/"
            utils.exec_cmd("perl -pi -e '{}' {}".format(pattern, cfg_file))
        # cron job
        with open("/etc/cron.d/letsencrypt", "w") as fp:
            fp.write(
                "0 */12 * * * root certbot renew "
                "--quiet --no-self-upgrade --force-renewal\n"
            )


def get_backend(config):
    """Return the appropriate backend."""
    if not config.getboolean("certificate", "generate"):
        return None
    if config.get("certificate", "type") == "letsencrypt":
        return LetsEncryptCertificate(config)
    return SelfSignedCertificate(config)
