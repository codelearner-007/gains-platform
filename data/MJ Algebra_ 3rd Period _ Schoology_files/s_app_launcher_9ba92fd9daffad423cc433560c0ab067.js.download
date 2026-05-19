var quickInstallAutoLaunchClicked = false;

Drupal.behaviors.sAppLauncher = function(context) {
  Drupal.settings.s_app = Drupal.settings.s_app || {};

  if(!quickInstallAutoLaunchClicked && typeof Drupal.settings.s_app != 'undefined'){
    if(Drupal.settings.s_app.auto_launch_quick_install){
      $('.app-quick-installer-popup').click();
      quickInstallAutoLaunchClicked = true;
    }
  }

  $("#schoology-app-loader:not(.sAppLauncher-processed)", context).addClass('sAppLauncher-processed').each(function(){
    if(Drupal.settings.s_app.launcher){
      var params = sAppLauncherGetParams({type: 'standard', isImport: false, url: location.href});
      var launchKey = params.appNid + '-' + params.realm +'-' + params.realmID;
      if(Drupal.settings.s_app.launcher.hasOwnProperty(launchKey)) {
        var contentWrapper = $('#content-wrapper');
        var csmSectionToggle = $('#csm-section-toggle');
        var launchSettings = Drupal.settings.s_app.launcher[launchKey];
        const postMessageEmbedParams = {
          post_message_embed_url: launchSettings.post_message_embed_url,
          post_message_embed_iframe_name: launchSettings.post_message_embed_iframe_name
        };
        var csmToggle = csmSectionToggle.length ? csmSectionToggle.html() : '';
        var output = Drupal.theme('sAppContainer', launchSettings.type, launchSettings.url, launchSettings.cookie_required, csmToggle, postMessageEmbedParams);
        contentWrapper.html(output);
        sAttachBehaviors(['sAppLauncher'], contentWrapper);

        sAppRegisterChannelListenerForUnsavedChanges(launchSettings.app_origin);
      }
    }
    $(this).remove();
  });

  $("#schoology-app-container:not(.sAppLauncher-processed)", context).addClass('sAppLauncher-processed').each(function(){
    // Listen for LTI app return redirect message
    sAppLauncherAddEventListenerForLtiFrameMessages();

    // Resize the iframe that contains the app so it takes up the maximum height remaining in the viewport affter
    // taking into account the header (#header) and the breadcrumbs area (#center-top)
    var appWindowObj = $(this);
    $(window).resize(function() {
      var new_height = $(this).height();
      $('#header:visible, #center-top:visible').each(function() {
          new_height -= $(this).outerHeight();
      });
      appWindowObj.height(new_height);
    }).trigger('resize');

    //hide the dropdown for courses, groups, and resources if the app iframe is clicked
    var bound = false;
    $('.primary-activities .clickable').each(function(){
      $(this).click(function(){
        if(!bound){
          var iframeMouseOver = false
          if($.browser.msie && $.browser.version.charAt(0) == 8){
            document.onfocusout = function(){ //need to use document.onfocusout for IE8
              if(iframeMouseOver){
                $('.activities-dropdown-wrapper').hide();
                bound = false;
              }
            };
          }
          else{
            $(window).bind('blur.sAppLauncher', function(){
              if(iframeMouseOver){
                $('.activities-dropdown-wrapper').hide();
                $(window).unbind('blur.sAppLauncher');
                bound = false;
              }
            });
          }

          appWindowObj.bind('mouseover',function(){
            iframeMouseOver = true;
          });
          appWindowObj.bind('mouseout',function(){
            iframeMouseOver = false;
          });
        }
        bound = true;
      });
    });

    // allow users to launch manually if auto-launch fails (popup blocker)
    $(".s-js-launch-button", appWindowObj).bind('click', function(e){
      e.preventDefault();
      if($(this).hasClass('disabled')) {
        return;
      }
      var newWin = sCommonOpenNewWindow($(this).attr('href'), {name: 'schoology-app'});
      if(newWin !== false) {
        $(this).addClass('disabled');
        $(this).prev('.app-launch-message').html(Drupal.t('Your app has been launched in a new window.'));
        newWin.focus();
      }
    });
    $('.s-js-launch-button', appWindowObj).trigger('click');
  });

  /**
   * s_tinymce insert resource app content form
   */
  $('#s-js-tinymce-resources-insert-form-wrapper:not(.sTinymceResourcesInsert-processed)', context)
    .addClass('sTinymceResourcesInsert-processed').each(function()
    {
      var contentEmbedForm = $('#s-tinymce-resources-insert-form', $(this));
      var appNid = parseInt( $('#edit-app-nid', contentEmbedForm).val() );
      var appType = $('#edit-app-type', contentEmbedForm).val();
      var realm = $('#edit-realm', contentEmbedForm).val();
      var realmId = parseInt( $('#edit-realm-id', contentEmbedForm).val() );
      var folderId = parseInt( $('#edit-folder-id', contentEmbedForm).val() );
      var fWeight = parseInt( $('#edit-fweight', contentEmbedForm).val() );

      var app = {};
      app['type'] = appType;
      app['isRTE'] = true;
      if(appType == 'resources') {
        app['url'] = '/resources/apps/'+ appNid +'/run';
      }
      else if(appType == 'lti') {
        app['url'] = '/apps/lti/'+ appNid +'/run/'+ realm +'/'+ realmId + '?f=' + folderId + '&fweight=' + fWeight;
      }
      // not supported?
      else {
        return;
      }

      sAppLauncher($('#s-js-resources-app-container', contentEmbedForm), app);
  });
}

Drupal.theme.prototype.sAppContainer = function(launchType, launchUrl, cookieRequired, csm_toggle, postMessageEmbedParams) {
  var template = '';

  if(cookieRequired) {
    template += '<div class="cookie-warning">';
    template += '<p class="app-launch-message">'+ Drupal.t('This app must be launched by clicking on its link on the left menu.') +'</p>';
    template += '</div>';
    return template;
  }

  if(launchType == 2) {
    template += '<div id="schoology-app-container" align="center">';
    template += '<p class="app-launch-message">'+ Drupal.t('We attempted to launch your app in a new window, but a popup blocker is preventing it from opening. Please disable popup blockers for this site.') +'</p>';
    template += '<a class="link-btn s-js-launch-button" href="'+ launchUrl +'">'+ Drupal.t('Launch App') +'</a>';
    template += '</div>';
  }
  else {
    if(csm_toggle){
      template += '<div id="schoology-csm_toggle" align="left">';
      template += '<p>'+ csm_toggle +'</p>';
      template += '</div>';
    }
    template += `
      <iframe id="schoology-app-container"
              frameborder="0"
              width="100%"
              height="800"
              allow="camera *; encrypted-media *; geolocation *; microphone *; midi *"
              src="${launchUrl}"
              name="schoology-app-container"
      ></iframe>`;

    if (!!postMessageEmbedParams.post_message_embed_url) {
      template += `
      <iframe id="${postMessageEmbedParams.post_message_embed_iframe_name}"
              style="display: none;"
              src="${postMessageEmbedParams.post_message_embed_url}"
              name="${postMessageEmbedParams.post_message_embed_iframe_name}"
      ></iframe>`;
    }
  }

  return template;
};

function sAppLauncher(target, app) {
  if(!Drupal.settings.s_app.launcher) {
    Drupal.settings.s_app.launcher = {};
  }
  var params = sAppLauncherGetParams(app);
  var launchKey = params.appNid + '-' + params.realm +'-' + params.realmID;

  function renderApp(launchSettings) {
    var url = launchSettings.url;

    if (url && $.isPlainObject(app.params)) {
      url += (url.indexOf('?') === -1 ? '?' : '&') + $.param(app.params);
    }

    // PE-128539: Add tabId to launch to avoid BroadcastChannel crosstalk
    url += `&tab_id=${sessionStorage.tabId}`;

    var postMessageEmbedParams = {
      post_message_embed_url: launchSettings.post_message_embed_url,
      post_message_embed_iframe_name: launchSettings.post_message_embed_iframe_name
    };

    var output = Drupal.theme('sAppContainer', launchSettings.type, url, launchSettings.cookie_required, '', postMessageEmbedParams);
    target.html(output);
    sAttachBehaviors(['sAppLauncher'], target);
  }

  if(Drupal.settings.s_app.launcher.hasOwnProperty(launchKey)) {
    renderApp( Drupal.settings.s_app.launcher[launchKey] );
    return;
  }

  sToggleActiveLoader('sAppLauncher', target);
  $.getJSON(params.settingsURI, function(data) {
    sToggleActiveLoader('sAppLauncher');

    Drupal.settings.s_app.launcher[launchKey] = data.body;
    renderApp( Drupal.settings.s_app.launcher[launchKey] );
  });
}

function sAppLauncherGetParams(app) {
  var q_params = {
    import_view: app.isImport ? 1 : 0
  };
  var url = '';
  var appNid = 0;
  var appRealm = '';
  var appRealmID = 0;
  var qParams = {};

  function parse_str(q_string, q_params) {
    if(q_string != '') {
      var q_string = q_string.split('&');
      for(i = 0; i < q_string.length; i++) {
        var key_val = q_string[i].split('=');
        q_params[ key_val[0] ] = key_val[1];
      }
    }
  }

  if(app.type == 'resources') {
    var parsed_url = app.url.match(/\/([0-9]+)\/run(\?)?(.*)/);
    appNid = parsed_url[1];
    appRealm = 'user';
    appRealmID = Drupal.settings.s_common.user.uid;
    url += appNid + '/' + app.type;
    parse_str(parsed_url[3], q_params);
  }
  else if(app.type == 'standard' || app.type == 'lti') {
    if(app.url.indexOf('/apps/school_apps/') != -1) {
      var parsed_url = app.url.match(/\/apps\/school_apps\/([0-9]+)\/configure(\?)?(.*)/);
      appNid = parsed_url[1];
      appRealm = 'school';
      appRealmID = Drupal.settings.s_common.user.school_nid;
    }
    else {
      var parsed_url = app.url.match(/\/([0-9]+)\/run\/([a-z]+)\/([0-9]+)(\?)?(.*)/);
      appNid = parsed_url[1];
      appRealm = parsed_url[2];
      appRealmID = parsed_url[3];
      qParams = getQueryParams(app.url);
    }
    url += appNid + '/' + app.type + '/' + appRealm + '/' + appRealmID;
    if(typeof app.isRTE != 'undefined' && app.isRTE == true){
      url += '&from=rte';
      if(qParams && typeof qParams.f != 'undefined') {
        url += '&f=' + String(qParams.f);
      }

      if(qParams && typeof qParams.fweight != 'undefined') {
        url += '&fweight=' + String(qParams.fweight);
      }
    }
  }

  if(url == '') {
    return false;
  }

  // we need to preserve the query strings for resources apps (import view, dropbox ..etc)
  var url_params = [];
  if(app.type == 'resources') {
    $.each(q_params, function(key, value) {
      url_params.push(key + "=" + encodeURIComponent(value));
    });
    url += '?' + url_params.join('&');
  }
  url = '/iapi/app/launcher/' + url;

  return {
    appNid: appNid,
    realm: appRealm,
    realmID: appRealmID,
    settingsURI: url
  };
}

function sAppLauncherClearCache(appNid) {
  // clear cached launch data since we store cookie preload attenpts in session
  for(var appKey in Drupal.settings.s_app.launcher) {
    if(appKey.split('-')[0] == appNid) {
      delete Drupal.settings.s_app.launcher[appKey];
      break;
    }
  }
}

/**
 * Register an "are you sure you want to leave" if there are unsaved changes
 * we want to make sure that the frame as has loaded before registering the app
 *
 * Sample usage of this behavior in an app:
 * ```
     <script src="https://app.schoology.com/sites/all/misc/jschannel.js"></script>
     <script src="https://app.schoology.com/sites/all/misc/schoology_api.js"></script>
     <script type="text/javascript">
       var schoologyApi = SchoologyApi.create({
            version: 'v1',
            context: 'app'
          });
       schoologyApi.setHasUnsavedChanges(true);
     </script>
 * ```
 * Note that the app should also register its own onbeforeunload for when the app
 * is opened outside of an iframe
 */
function sAppRegisterChannelListenerForUnsavedChanges(app_origin) {
  sAppIframeLoadingAppUrl(function() {
    var app = SchoologyApp.register('schoology-app-container', app_origin, 'app');
    app.setHasUnsavedChanges(function(event, params){
      var hasUnsavedChanges = params.hasOwnProperty('hasUnsavedChanges') && params.hasUnsavedChanges;
      if (hasUnsavedChanges) {
        window.onbeforeunload = function (event) {
          // Based on https://developer.mozilla.org/en-US/docs/Web/Events/beforeunload, only IE shows a custom
          // message. All other browser use generic text.
          event.returnValue = Drupal.t('You have not saved your work. Are you sure you want to leave this page?');
        };
      } else {
        window.onbeforeunload = null;
      }
    });
  });
}

/**
 * Calls the given callback once the app iframe is loading the actual app URL
 * (as opposed to the local SAML initialization endpoints). This is helpful with
 * the postMessage API since a specific origin is required when building the messaging channel.
 * Initialization will otherwise fail if it starts and the iframe still points to
 * schoology's own SAML iniialization URLs.
 *
 * - App Launch
 * - IFrame loads app.schoology.com/apps/login/saml/initial
 * - That page redirects to the actual app URL (e.g. www.example.com/app)
 *      <-- This is when we want JSChannel to be initialized
 * - Browser loads www.example.com/app
 *
 * @param {func} callback
 */
function sAppIframeLoadingAppUrl(callback) {
  // While the iframe src is still on the same domain, the app is still going
  // through the login workflow. Once the iframe src points to a different domain,
  // the browser will throw a DOMException since it blocks accessing cross-origin frames.
  // At that point, we know that the app has begun to load and we can now execute the callback
  try {
    // This will succeed if it's still logging in
    // and throw an exception if it's cross domain
    var iframe = document.getElementById('schoology-app-container');
    var iframeSrc = iframe.contentWindow.location.href;
    window.setTimeout(function() { sAppIframeLoadingAppUrl(callback) }, 1000);
  } catch (e) {
    callback();
  }
}

/**
 * @param {boolean} open (Optional)
 */
function sAppToggleSpinner(open = true) {
  // this is hardcoded reference to the spinner image,
  //   used because it is more efficient than pulling in all of React/DS
  //   (but it may go out-of-sync with DS spinner in future)
  var spinnerUrl = 'https://ui.schoology.com/design-system/assets/loading-spinner-primary.bff7e5a477da99260604091a58a62019.gif';

  var $overlay = $('#schoology-app-container-spinner');

  var $targetParent = $('#schoology-app-container');
  if ($targetParent.closest('.popups-body').length) {
    $targetParent = $targetParent.closest('.popups-body');
  } else if ($targetParent.closest('#library-main').length) {
    $targetParent = $targetParent.closest('#library-main');
  }

  if (!$overlay.length && $targetParent.length > 0) {
    // create spinner overlay element
    $overlay = $('<div id="schoology-app-container-spinner"><img src="' + spinnerUrl + '" alt="' + Drupal.t('Loading') + '"></div>');
    $targetParent.append($overlay);
  }

  if ($overlay.length && $targetParent.length) {
    // show/hide overlay
    open && $targetParent.length > 0 ? $targetParent.css('position', 'relative') : $targetParent.css('position', '');
    open ? $overlay.show() : $overlay.hide();
  }
}

/**
 * When an LTI tool calls the 'return url' that Schoology sent at LTI launch,
 * the return url handler may post a message from iframe to Sgy host window.
 * This method sets a listener for that message.
 *
 * @see AppReturnController::handleAppReturnContentNav
 * @see AppReturnController::handleAppReturnRealmContext
 */
function sAppLauncherAddEventListenerForLtiFrameMessages() {
  var listenerType = 'message';

  var listener = function (event) {
    if (event.origin === window.location.origin && event.data?.actionType) {
      switch (event.data.actionType) {
        case 'addMessage':
          var { message, level } = event.data;
          addMessages([{'value': message}], level);
          break;

        case 'redirect':
          var { realm, realmId } = event.data;
          var url = `/${realm}/${realmId}`;
          window.location.href = url;
          break;

        case 'transferHistory':
          window.location.href = '/settings/transfers';
          break;
      }
    }
  }

  window.addEventListener(listenerType, listener);
}
