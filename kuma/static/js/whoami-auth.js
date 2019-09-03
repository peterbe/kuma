(function() {
    'use strict';

    // function getWikiAbsoluteURL() {
    //     // XXX Use your imagination!
    //     return "http://wiki.mdn.localhost:8000";
    // }

    function isLoggedIn(whoami, cached) {

        var $loggedIn = $('#logged-in');

        // XXX needs to pick up the *locale* from the current URL
        var profileURL = `/en-US/profiles/${whoami.username}`;
        var editProfileURL = profileURL + '/edit';
        $('a[href="#template-profile-url"]', $loggedIn).attr('href', profileURL);
        $('a[href="#template-edit-profile-url"]', $loggedIn).attr('href', editProfileURL);
        $('a.user-url img.avatar', $loggedIn)
            .attr('src', whoami.gravatar_url.small)
            .attr('alt', whoami.username);
        $('a.user-url span.login-name', $loggedIn).text(whoami.username);
        // Once the gravatar has loaded, make the switch.
        var gravatarImg = new Image();
        // This must come before .decode() otherwise Safari will
        // raise an EncodingError.
        gravatarImg.src = whoami.gravatar_url.small;
        gravatarImg.decode().then(function() {
            $('#toolbox .nav-tools:hidden').fadeIn();
            $('#not-logged-in').hide();
            $loggedIn.fadeIn();
        }, function(err) {
            console.warn(`Failed to decode gravatarImg`);
            // YOLO!
            $('#not-logged-in').hide();
            $loggedIn.fadeIn();
        })

    }

    function revertIsLoggedIn() {
        // Thanks to sessionStorage caching, it displayed that you were
        // logged in, but it turns out you're not.
        $('#toolbox .nav-tools:hidden').hide();
        $('#logged-in').hide();
        $('#not-logged-in').show();
    }

    var whoamiLocal = sessionStorage.getItem('whoami');
    if (whoamiLocal) {
        isLoggedIn(JSON.parse(whoamiLocal), true);
    }

    fetch('/api/v1/whoami').then(function(response) {
        if (!response.ok) {
            console.error("Bad response from /api/v1/whoami", response);
        } else {
            return response.json().then(function(whoami) {
                if (whoami.is_authenticated) {
                    sessionStorage.setItem('whoami', JSON.stringify(whoami));
                    isLoggedIn(whoami);
                } else {
                    sessionStorage.removeItem('whoami');
                    if (whoamiLocal) {
                        revertIsLoggedIn();
                    }
                }
            });
        }
    })


})();
