Drupal.behaviors.sAppMenu = function(context) {

  // Launch the cookie preload popup as soon as an app is launched
  $("#menu-s-apps-list .app-link:not(.sAppMenu-processed), .resources-app-list .s-js-app-launch.resources-app-title:not(.sAppMenu-processed)", context).addClass('sAppMenu-processed').each(function(){
    var link = $(this);
    var isResourceApp = link.hasClass('resources-app-title');
    
    // This needs to be bound by a user's click behavior; otherwise,
    // the popup will be blocked by the browser
    link.click(function(e){
      var appNid, appUrl, cookiePreloadUrl;

      if(!isResourceApp) {
        appNid = link.parents('.app-link-wrapper').attr('id').split('-')[2];
        appUrl = link.attr('href');
      }
      else {
        appNid = link.parents('.s-app-resource-app').attr('id').split('-')[1];
        appUrl = link.attr('href');
      }

      cookiePreloadUrl = sCommonGetSetting('s_app', 'cookie_preload_urls', appNid);
      if(cookiePreloadUrl) {
        // Prevent the app from launching immediately
        e.preventDefault();
        if(isResourceApp) {
          // for resource apps, also prevent other click handlers before running cookie preloader
          e.stopImmediatePropagation();
        }

        sAppMenuCookiePreloadRun(appNid, cookiePreloadUrl, function(){
          if(!isResourceApp) {
            window.location = appUrl;
          }
          else {
            // clear cached launch data since we store cookie preload attempts in session
            sAppLauncherClearCache(appNid);
            sAppMenuCookiePreloadDelete(appNid);
            // now trigger app click since the cookie preloader is done
            link.trigger('click.s-js-library-ajax-links');
          }
        });
      }
    });
  });
}

function sAppMenuCookiePreloadRun(appNid, cookiePreloadUrl, afterPreloadCallback) {
  // Open the cookie preload window
  window.open(cookiePreloadUrl,'cookiepreloader','width=100,height=100,toolbar=0,menubar=0,location=0,status=0,scrollbars=0,resizable=0,left=0,top=0');

  // Make a synchronous call to mark this app's cookies as loaded.
  // If the app loads before this call is made, it might end up in a browser loop.
  $.ajax({
    url: '/apps/' + appNid + '/cookies_loaded',
    async: false
  });

  // After a short moment to allow the popup to load, continue launching the app
  setTimeout(afterPreloadCallback, 800);
}

function sAppMenuCookiePreloadSet(data) {
  Drupal.settings.s_app = Drupal.settings.s_app || {};
  Drupal.settings.s_app.cookie_preload_urls = Drupal.settings.s_app.cookie_preload_urls || {};
  for(var appKey in data) {
    Drupal.settings.s_app.cookie_preload_urls[appKey] = data[appKey];
  }
}

function sAppMenuCookiePreloadDelete(appNid) {
  delete Drupal.settings.s_app.cookie_preload_urls[appNid];
}
