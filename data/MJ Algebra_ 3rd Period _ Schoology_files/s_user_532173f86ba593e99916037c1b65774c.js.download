Drupal.behaviors.s_user = function(context){

    $('#s-user-custom-notifications-form:not(.sUser-processed)').addClass('sUser-processed').each(function(){
        //handle select all functionality in custom notification form
        var form = $(this);
        var selectAll = $('.select-all', form);
        selectAll.click(function(){
            var checked = $(this).is(':checked');
            $('.realm-setting', form).each(function(){
                $(this).prop('checked', checked);
            });
        });

        $('.edit-select-all-wrapper', form).click(function(){
            $('input', this).click();
        });


        $('.realm-setting').each(function(){
            var realmSetting = $(this);
            realmSetting.change(function(){
                if(!realmSetting.prop('checked') && selectAll.prop('checked')){
                    selectAll.prop('checked', false);
                }
            });
        });

        $('.cancel-btn', form).click(function(e){
            //reset the value of the correspoding select form in the notifications setting to its original value
            var setting = $('.setting-name', form).val();
            var selectVal = $('.original-setting', form).html();
            $('select[name=' + setting + ']').selectmenu('value', selectVal);
            var popup = Popups.activePopup();
            if(popup != null){
                popup.close();
            }
            e.preventDefault();
        });

    });

    $('.notifications-header:not(.sUser-processed)').addClass('sUser-processed').each(function(){
        // handles reset to default for notification settings
        if(Drupal.settings.s_user != 'undefined' && typeof Drupal.settings.s_user.notif_defaults != 'undefined'){
            var setting = Drupal.settings.s_user;
            $('.reset-default').click(function(){
                $('select.notif-setting-select').each(function(){
                    var name = $(this).attr('name');
                    if(typeof setting.notif_defaults[name] != 'undefined'){
                        $(this).selectmenu('value', setting.notif_defaults[name]);
                    }
                });
            });
        }
    });

    $('#s-user-set-notifications-form:not(.sUser-processed)').addClass('sUser-processed').each(function(){
        //open popup for for when "custom" is selected
        $('select.notif-setting-select').each(function(){
            var select = $(this);
            select.selectmenu({
                style: 'dropdown'
            });
            select.change(function(){
                if(select.val() == '2'){
                    var href = '/user/custom_notification/' + select.attr('name');
                    Popups.openPath(this, {
                        href : href,
                        ajaxForm : false,
                        extraClass : 'popups-custom-notification popups-medium'
                    }, window);
                }
            });
        });
    });

    $("a.show-code").click(function(){
        var value = $(this).attr('id');
        var value = value.split("-");
        var html = '<div class="formatted-code">Code: '+value[1]+'</div>';
        $.prompt(html);
        return false;
    });

    $("input#action-select-all").click(function(){
        var parent = $(this);
        $("#s-user-manage-activation-form table input:checkbox").each(function(){
            if($(this).prop('checked')){
                $(parent).prop('checked', false);
                $(this).prop('checked', false);
            }
            else{
                $(parent).prop('checked', true);
                $(this).prop('checked', true);
            }
        });
    });

    $('#s-user-edit-calendar-feed-settings-form:not(.sUser-processed)').addClass('sUser-processed').each(function(){
        $('#webcal-addr', $(this)).focus(function(){
            document.getElementById('webcal-addr').select();
        }).mouseup(function(e){
            e.preventDefault();
        });

    });

    $('#s-user-profile-editor-profile-form:not(.sUser-processed)').addClass('sUser-processed').each(function(){
        $('textarea', $(this)).elastic();

        var learnerWrapper = $('.learner-style-wrappper');
        var defaultLearnerRadioBtnWrapper = $('#edit-profile-about-learner-style-0-wrapper', learnerWrapper);
        var defaultLeanerRadioBtn = $('input[type=radio]', defaultLearnerRadioBtnWrapper);
        defaultLearnerRadioBtnWrapper.hide();
        sCommonFormRadioGroup(learnerWrapper, defaultLeanerRadioBtn);
    });

    $('#s-user-personal-account-settings-form:not(.sUser-processed)').addClass('sUser-processed').each(function(){
      var form  = $(this);
      $('.timezone-select-time .timezone-use-list', form).bind('click', function(){
        $(this).parent().hide();
        $('.timezone-select-timezone', form).show();
        $('#edit-timezone-select-type', form).val('timezone');
      });
      $('.timezone-select-timezone .timezone-use-time', form).bind('click', function(){
        $(this).parent().hide();
        $('.timezone-select-time', form).show();
        $('#edit-timezone-select-type', form).val('time');
      });

      showCurrentPasswordWhenEmailChanges(form);

      //only display the show preferred name dropdown if a preferred name has been set
      $('#edit-user-name-first-preferred').on('keydown paste input', function(e){
        var $textbox = $(this);
        var hasPreferredName = !!$textbox.val().length;
        var $namePreferredWrapper = $textbox.closest('.name-first-preferred-wrapper');
        var $usePreferredName = $('.use-name-first-preferred-wrapper');
        var usePreferredNameVisible = !$usePreferredName.hasClass('hidden');
        if(hasPreferredName != usePreferredNameVisible){
          $usePreferredName.toggleClass('hidden', usePreferredNameVisible);
          $namePreferredWrapper.toggleClass('has-preferred-first-name', hasPreferredName);
        }
      });
    });

    $('.s-js-name-title-wrapper:not(.sUser-processed)', context).addClass('sUser-processed').each(function(){
      var titleWrapper = $(this),
          customField = $('.s-js-name-title-custom', titleWrapper);
      $('.s-js-name-title-select', titleWrapper).change(function(e){
        if($(this).val() == 'custom'){
          titleWrapper.addClass('s-js-name-title-custom-enabled');
        }
        else{
          titleWrapper.removeClass('s-js-name-title-custom-enabled');
          customField.val('');
        }
      }).triggerHandler('change');
    });

    //performs logout when an account is deleted
    if($('.logout-exec').text() == '1'){
        var url = location.href;
        index = url.indexOf('settings/');

        var logoutHref = '/logout?';
        if (Drupal.settings.s_common.hasOwnProperty('logout_token')){
            logoutHref += 'ltoken='+Drupal.settings.s_common.logout_token+'&';
        }
        logoutHref += 'destination=home.php?deleted';
        newUrl = url.substring(0,index) + logoutHref;
        location.href = newUrl;
    };



   $('.profile-picture-wrapper:not(.sUser-processed)', context).addClass('sUser-processed').each(function(){
        var wrapper = $(this);
        var link = $('.edit-profile-picture-hover', wrapper);
        var pic = $('.profile-picture', wrapper);
        var uploader = $('#profile-picture-uploader-wrapper', wrapper);

        link.bind('click', function(){
          if(uploader.is(':visible')){
            uploader.hide();
          }
          else {
            uploader.show();
          }
        });
        $('body').bind('click', function(e){
            var target = $(e.target);
            if(!target.hasClass('profile-picture-wrapper') && target.parents('.profile-picture-wrapper').length == 0){
              uploader.hide();
            }
          });

        pic.bind('s_profile_picture_uploaded', function(e, path){
	      	$('img', $(this)).attr('src', path).removeAttr('height');
	        uploader.hide();
	      });

      });

  // remove a push notification device on the notifications settings page
  $('.push-remove:not(.sUser-processed)', context).addClass('sUser-processed').bind('click', function(e){
    e.preventDefault();

    var linkObj = $(this);
    var deviceNameString = '<span class="confirm-remove-device-name">' + linkObj.siblings('.push-os').html() + '</span>';
    var removeDevicePopupBody = '<span class="confirm-message">' +
      Drupal.t('Are you sure you want to deactivate !device_name?', {"!device_name" : deviceNameString}) +
      '</span>';

    sCommonConfirmationPopup({
      title: Drupal.t('Deactivate Device'),
      body: removeDevicePopupBody,
      extraClass: 'push-remove',
      confirm: {
        text: Drupal.t('Deactivate'),
        func: function(){
          $.ajax(linkObj.attr('href'), {
            data: {ajax: true},
            success: function(data){
              if(data.body){
                $('#content-wrapper').html(data.body);
                if(data.messages){
                  var mainWrapperObj = $('#main-content-wrapper');
                  mainWrapperObj.children('.messages').remove();
                  mainWrapperObj.prepend(data.messages);
                }
                Drupal.attachBehaviors($('#main-content-wrapper'));
              }
            },
            complete: function(){
              Popups.activePopup().close();
            }
          });
        }
      }
    });
  });
}

function repositionZClipboard(){
    var offset = $('#invite_link').offset();
    var pOffset = $('.popups-box').offset();
    $('.zclipboard').css('left', offset.left - pOffset.left);
    $('.zclipboard').css('top', offset.top - pOffset.top);
}

/**
 * Show current password field if email fields are changed
 */
function showCurrentPasswordWhenEmailChanges(form) {
  var emailFields = [
    ['emailOriginal', $('#edit-user-login-identifiers-primary-email', form)],
    ['emailAltOriginal', $('#edit-user-mail-alternate', form)],
  ];
  var $currentPasswordField = $('#edit-user-current-password-wrapper', form);
  emailFields.forEach(function(emailField) {
    // Store original values of email / alternate email fields
    var $field = emailField[1];
    form.data(emailField[0], $field.attr('data-original'));

    // On change, show the password field if either of the fields are different than before
    emailField[1].bind('change', function() {
      var changed = false;
      emailFields.forEach(function(emailFieldCheck) {
        if(emailFieldCheck[1].val() !== form.data(emailFieldCheck[0])) {
          changed = true;
        }
      });
      $currentPasswordField.toggle(changed);
    })
      // Trigger change on form load to exec logic on failed form validation
      .change();
  });

  // Add a "required" marker to the current password field (we don't want to use
  // the form definition #required=true because we want to allow it to be blank
  // if emails were not changed
  $('label', $currentPasswordField).append('<span class="form-required" title="This field is required.">*</span>');
}
