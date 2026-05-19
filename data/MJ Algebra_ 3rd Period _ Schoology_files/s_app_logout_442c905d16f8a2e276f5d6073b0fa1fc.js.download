Drupal.behaviors.sAppLogout = function(context) {
	$('#header:not(.sAppLogout-processed)').addClass('sAppLogout-processed').on('click', 'a.logout', function(e){
		// Prevent default link behavior immediately
		e.preventDefault();
		
		if (window.sAppLtiSubmissionSessionManager && window.sAppLtiSubmissionSessionManager.clearLtiSessions && window.sAppLtiSubmissionSessionManager.hasLtiSessionsToClear()) {
			window.sAppLtiSubmissionSessionManager.clearLtiSessions()
				.then(function() { proceedWithLogout(); })
				.catch(function() { proceedWithLogout(); });
		} else {
			proceedWithLogout();
		}
		
		function proceedWithLogout() {
			$.ajax({
				type: 'GET',
				url: '/apps/logout/saml',
				cache: false,
				dataType: 'json',
				success: function(data){
					if (!Drupal.settings.hasOwnProperty('s_app')){
						Drupal.settings.s_app = {};
						Drupal.settings.s_app.num_assocs = data.num_associations;
					}
					var buttons = {};
					var popup = new Popups.Popup();
					popup.extraClass = 'popups-small app-logout no-buttons';
					if(data.num_associations > 0){
						Popups.open(popup, Drupal.t('App Logout'), data.html, buttons);
						sAppLogoutTimer('#' + $('.popups-box').attr('id'));
						Drupal.attachBehaviors();
					}
					//If no apps were logged into then we want a plain redirect to the normal logout page
					else{
						window.location = '/logout?force&ltoken='+sAppLogoutGetLogoutToken();
					}
				},
				error: function(html){
					window.location = '/logout?force&ltoken='+sAppLogoutGetLogoutToken();
				}
			});
		}
		
		return false;
	});
}

function sAppLogoutSuccess(data){
  var wrapper = $('tr#app-' + data);

  if(wrapper.hasClass('done')){
    return;
  }

  $('.pending', wrapper).hide();
  $('.success', wrapper).show();

  wrapper.addClass('done');

  Drupal.settings.s_app.num_assocs--;
  if(Drupal.settings.s_app.num_assocs <= 0){
	  window.location = '/logout?ltoken='+sAppLogoutGetLogoutToken();
  }
}

//Allow apps x seconds to logout. After that, show error and a manual logout link.
function sAppLogoutTimer(context){
	$('#app-logout-wrapper:not(.sAppLogout-processed)', context).addClass('sAppLogout-processed').each(function(){
    var wrapper = $(this);
    var time = 10;
    setTimeout(function(){
      $('table tr:not(.done)', wrapper).each(function(){
        var row = $(this);

        $('.pending', row).hide();
        $('.error', row).show();

        row.addClass('done');
      });

      $('#logout-force').show();
      $('.popups-box').removeClass('no-buttons');
      sPopupsResizeCenter();
    }, time*1000)
  });
}

// Return logout token if it is provided by Drupal.settings.
function sAppLogoutGetLogoutToken(){
  return Drupal.settings.s_common.hasOwnProperty('logout_token')
    ? Drupal.settings.s_common.logout_token
    : '';
}
