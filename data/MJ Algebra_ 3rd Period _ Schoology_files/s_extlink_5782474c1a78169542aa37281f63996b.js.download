/**
 * Bind a click handler to all links on the site that will check if they are external links
 * This will be delegated at the body level and should only execute once
 *
 * @param DOMElement context
 */
function extlinkAttach(context) {
  var $context = context == document ? $(document.body) : $(context);
  if($context.closest('.sExtlink-processed').length){
    // since the event is delegated, this will only need to be done once at the highest level
    return;
  }

  $context.addClass('sExtlink-processed');

  // Strip the host name down, removing subdomains or www.
  //pattern matching here is strange, e.g. it will behave differently for example if on www.abcd.ucd.edu and www.abcd.ucdavis.edu
  var host = window.location.host.replace(/^(([^\/]+?\.)*)([^\.]{4,})((\.[a-z]{1,4})*)$/, '$3$4'),
      subdomain = window.location.host.replace(/^(([^\/]+?\.)*)([^\.]{4,})((\.[a-z]{1,4})*)$/, '$1'),
      extInclude = false,
      extExclude = false,
      subdomains, internalLink;

  // Determine what subdomains are considered internal.
  if (Drupal.settings.extlink.extSubdomains) {
    subdomains = "([^/]*\.)?";
  }
  else if (subdomain == 'www.' || subdomain == '') {
    subdomains = "(www\.)?";
  }
  else {
    subdomains = subdomain.replace(".", "\.");
  }

  // Build regular expressions that define an internal link.
  internalLink = new RegExp("^https?://" + subdomains + host + '/', "i");

  // Extra internal link matching.
  if (Drupal.settings.extlink.extInclude) {
    extInclude = new RegExp(Drupal.settings.extlink.extInclude.replace(/\\/, '\\'));
  }

  // Extra external link matching.
  if (Drupal.settings.extlink.extExclude) {
    extExclude = new RegExp(Drupal.settings.extlink.extExclude.replace(/\\/, '\\'));
  }

  /**
   * Determine if a url is an external URL
   * Also utilizes a whitelist and blacklist to override default behavior
   *
   * @param string url
   * @return bool
   */
  function urlIsExternal(url){
    var url = url.toLowerCase();

    // don't bother with links that are not using the http(s) protocol
    if(url.indexOf('http') !== 0){
      return false;
    }

    // if it's an internal link and it's not blacklisted (extInclude means consider it external)
    if(url.match(internalLink) && !(extInclude && url.match(extInclude))){
      return false;
    }

    // if the url is whitelisted (a bit backwards since normally blacklist should override whitelist)
    if(extExclude && url.match(extExclude)){
      return false;
    }

    return true;
  }

  // when clicking on links which are NOT internal and are using the http protocol
  // open it in a new tab so the user does not navigate out
  $context.on('click', 'a', function(e){
    var $link = $(this),
        url = this.href; // this will resolve the full url with domain even if the href is just the URI portion
    if($link.hasClass('s-extlink-direct')){
      // override behavior with this class
      return;
    }

    if(urlIsExternal(url)){
      e.preventDefault();
      window.open('/link?path='+encodeURIComponent($link.attr('href')));
    }
  });
}

Drupal.behaviors.extlink = function(context){
  if( Drupal.settings.extlinkExtras && Drupal.settings.extlinkExtras.disabled )
    return;

  /*
    we have to disable this functionality for respondus since external links will not open
    properly in high security mode. The respondus browser will open external links by default in
    a new window; further navigation in the new/external window will be blocked.
   */
  if(typeof sAppLdbGetSecurityLevel == "undefined") {
    extlinkAttach(context);
  }
  else if(typeof sAppLdbGetSecurityLevel != "undefined" && sAppLdbGetSecurityLevel() != 'restricted') {
    extlinkAttach(context);
  }

  var mailtoClass = sCommonGetSetting('extlink', 'mailtoClass');
  if(mailtoClass) {
    $('a:not(.sExtlink-processed)', context).addClass('sExtlink-processed').each(function(){
      var $link = $(this),
          href = $link.attr('href') || '';
      // Apply the "mailto" class to all mailto links not containing images.
      if(href.indexOf('mailto:') === 0 && $link.find('img:first').length === 0){
        $link.addClass(mailtoClass);
        if($link.css('display') == 'inline'){
          $link.after('<span class=' + mailtoClass + '></span>');
        }
      }
    });
  }
}
