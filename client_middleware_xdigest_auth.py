"""
Digest authentication middleware for aiohttp client.

This middleware implements HTTP Digest Authentication according to RFC 7616,
providing a more secure alternative to Basic Authentication. It supports all
standard hash algorithms including MD5, SHA, SHA-256, SHA-512 and their session
variants, as well as both 'auth' and 'auth-int' quality of protection (qop) options.
"""

from yarl import URL
from aiohttp import (DigestAuthMiddleware, ClientResponse)
from aiohttp import client_middleware_digest_auth as cmda


class XdigestAuthMiddleware(DigestAuthMiddleware):
    """
    This class implements HTTP Digest Authentication middleware for aiohttp client sessions.
    It extends the base DigestAuthMiddleware to patch Fronius special authentication behavior,
    which deviates from standard RFC 7616 in the following ways:
    1. Instead of sending a 401 Unauthorized response with a www-authenticate header, the server
    uses X-WWW-Authenticate (see leading X- prefix) as the header parameter
    """

    def _authenticate(self, response: ClientResponse) -> bool:
        """
        Takes the given response and tries digest-auth, if needed.

        Returns true if the original request must be resent.
        """
        if response.status != 401:
            return False

        # For Fronius, www-athenticate is replaced by X-WWW-Authenticate
        auth_header : str = response.headers.get("X-WWW-Authenticate", "")
        if not auth_header:
            return False  # No authentication header present

        method, sep, headers = auth_header.partition(" ")
        if not sep:
            # No space found in X-WWW-Authenticate header
            return False  # Malformed auth header, missing scheme separator

        if method.lower() != "digest":
            # Not a digest auth challenge (could be Basic, Bearer, etc.)
            return False

        if not headers:
            # We have a digest scheme but no parameters
            return False  # Malformed digest header, missing parameters

        # We have a digest auth header with content
        if not (header_pairs := cmda.parse_header_pairs(headers)):
            # Failed to parse any key-value pairs
            return False  # Malformed digest header, no valid parameters

        # Extract challenge parameters
        self._challenge = {}
        for field in cmda.CHALLENGE_FIELDS:
            if value := header_pairs.get(field):
                self._challenge[field] = value

        # Update protection space based on domain parameter or default to origin
        origin = response.url.origin()

        if domain := self._challenge.get("domain"):
            # Parse space-separated list of URIs
            self._protection_space = []
            for uri in domain.split():
                # Remove quotes if present
                uri = uri.strip('"')
                if uri.startswith("/"):
                    # Path-absolute, relative to origin
                    self._protection_space.append(str(origin.join(URL(uri))))
                else:
                    # Absolute URI
                    self._protection_space.append(str(URL(uri)))
        else:
            # No domain specified, protection space is entire origin
            self._protection_space = [str(origin)]

        # Return True only if we found at least one challenge parameter
        return bool(self._challenge)
