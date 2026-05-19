Drupal.behaviors.sCourseMaterialsFolders = function(context) {

  // Click behavior for link descriptions, since you can't have <a> tags wrap other <a> tags
  // which would be possible with rich text descriptions
  $('.materials-folder.item-info:not(.sCourseMaterialsFolders-processed)', context).addClass('sCourseMaterialsFolders-processed').each(function(){
    var folder = $(this);
    // Will not trigger if the folder-title doesn't contain an 'a' tag (e.g. permission denied)
    var folderTitleLink = $('.folder-title a', folder);
    var folderDescription = $('.folder-description', folder);
    if(folderDescription.hasClass('description-clickable')){
      folderDescription.bind('click', function(e){
        // Ignore if the target is a link
        if(!$(e.target).is('a')){
          // Use vanilla JS to follow the href
          folderTitleLink[0].click();
        }
      })
    }
  });

  (function(){
    /**
     * Refresh the sortable tbody within the folder tree structure.
     * This is needed to link all the sortable table bodies after a subdirectory is opened.
     * This occurs when dragging an item over a folder for a period of time and a subtree is opened.
     *
     * @param object subtreeContext
     */
    function refreshSortableContent(subtreeContext){
      subtreeContext.closest('#folder-contents-table').find('tbody.ui-sortable').each(function(k, tbodyEl){
        // Make the sortable plugin refresh upon ajax completion
        // (to allow handling of dynamic folder expansion AJAX
        $(tbodyEl).sortable('refresh');
      });
    }

    /**
     * Toggle the visibility of the folder's content based on the expander object.
     *
     * @param object $expander  the expander element that is linked to the folder being expanded
     * @param bool show  whether this is a show or hide operation
     */
    function toggleSubtree($expander, show){
      var $subtree = $expander.siblings('.folder-subtree'),
          $subtreeLinks = $subtree.find('.action-links-wrapper'),
          $description = $expander.parent().find('.s-js-folder-description'),
          $title = $expander.parent().find('.folder-title'),
          show = show || false,
          folderId = $expander.closest('.material-row-folder').attr('id').split('-')[1];

      var easing = 'easeInQuad',
          duration = 300;
      function toggleVisibility(show_subtree){
        if(show_subtree){
          descFunc = 'slideUp';
          subtreeFunc = 'slideDown';
        }
        else{
          descFunc = 'slideDown';
          subtreeFunc = 'slideUp';
        }
        $description[descFunc]({
          duration: duration,
          easing: easing
        });
        // hidding the action links wrapper since they are positioned absolutely and will appear in an unsightly manner
        // during the course of the animation
        $subtreeLinks.hide();
        $subtree[subtreeFunc]({
          duration: duration,
          easing: easing,
          done: function(){
            $subtreeLinks.show();
          }
        });
      }

      if(show){
        $expander.find('.visually-hidden').text(Drupal.t('Collapse folder.'));
        // If subtree was already loaded, show it
        if($subtree.length){
          toggleVisibility(true);
        }
        // Load the subtree
        else {
          $loader = $('<img class="pending" src="/sites/all/themes/schoology_theme/images/ajax-loader.gif" alt="' + Drupal.t('Loading') + '" />');
          $subtree = $('<div class="folder-subtree"></div>');
          $expander.parent().append($subtree);

          $title.after($loader);

          $.ajax({
            dataType: 'json',
            url: window.location.pathname,
            data: {
              ajax: 1,
              f: folderId
            },
            success: function(contents){
              contents = $(contents);

              // Do a little bit of cleanup
              // Since the helper function we use creates a form,
              // remove the form wrapper and other form artifacts
              $('form>div', contents).unwrap();
              $('[name=form_build_id], [name=form_token], [name=form_id]', contents).remove();
              $loader.remove();
              $subtree.hide().html(contents);
              toggleVisibility(true);
              Drupal.attachBehaviors($subtree);
              $('tr td.actions', $subtree).sActionLinks({ hidden: false, wrapper: '.action-links-wrapper' });

              var foldersActionPush = $(document).data('sCourseMaterialsFoldersActionPush');
              if(foldersActionPush && foldersActionPush.length){
                var fid = foldersActionPush.pop();
                var $expander = $('#f-' + fid + ' > td.folder-contents-cell > .folder-expander');
                if(!$expander.hasClass('expanded')){
                  $expander.click();
                }
                $(document).data('sCourseMaterialsFoldersActionPush', foldersActionPush);
              }
              else{
                refreshSortableContent($subtree);
              }
            },
            error: function(){
              $subtree.html('<div class="error">' + Drupal.t('There was an error while loading the folder content. Please reload this page and try again.') + '</div>');
              refreshSortableContent($subtree);
            }
          });
        }
      }
      else{
        $expander.find('.visually-hidden').text(Drupal.t('Expand folder.'));
        toggleVisibility(false);
      }
    }

    // Behavior for folder AJAX expanders
    $('.folder-contents-cell .folder-expander:not(.sCourseMaterialsFolders-processed)', context ).addClass('sCourseMaterialsFolders-processed').each(function(){
      var $expander = $(this);
      $expander.click(function(){
        var show = !$expander.hasClass('expanded');
        $expander.toggleClass('expanded');
        toggleSubtree($expander, show);
      });
    });
  })();

  // Keep track of actionlink clicks to re-expand the tree
  // after content refresh from popups
  // Only do this if there is a #folder-contents-table
  if($('#folder-contents-table').length){
    $('body:not(.sCourseMaterialsFolders-processed)', context).addClass('sCourseMaterialsFolders-processed').each(function(){
      $(document).bind('popups_open_path', function(event, element, href){
        var target = $(element).parents();
        // Handle the action if the popup source is action-links-wrapper or a descendant
        if(target.hasClass('action-links-wrapper') || target.closest('.action-links-wrapper').length){
          var foldersActionPush = [];

          // Start from the subtree div so it doesn't count the current folder
          target.closest('.subtree-folder-contents-table').parents('tr.material-row-folder').each(function(){
            foldersActionPush.push($(this).attr('id').split('-')[1]);
          });

          if(foldersActionPush && foldersActionPush.length){
            // Store this array in a data field rather than a global
            // variable since the AJAX success functions don't play nice
            // with global variables
            $(document).data('sCourseMaterialsFoldersActionPush', foldersActionPush);
          } else {
            $('.folder-expander.expanded').trigger('click');
          }

          location.hash = 'foldersexpanded=' + foldersActionPush.join(',');
        }
        if(target.closest('#course-materials-action-links-inline').length){
          var foldersActionPush = [];
          var materialsRowAddId = target.closest('#course-materials-action-links-inline').data('materialsRowAddId');
          if(materialsRowAddId){
            $('#' + materialsRowAddId).parents('tr.material-row-folder').each(function(){
              foldersActionPush.push($(this).attr('id').split('-')[1]);
            });
          }
          if(foldersActionPush.length){
            location.hash = 'foldersexpanded=' + foldersActionPush.join(',');
          }
        }
      }).bind('popups_form_success', function(event, popup, data){
        // Once the form succeeds, check to see if there are any fids
        // in the stored path - if so, ensure they're expanded
        var foldersActionPush = $(document).data('sCourseMaterialsFoldersActionPush');
        if(foldersActionPush && foldersActionPush.length){
          var fid = foldersActionPush.pop();
          var expander = $('#f-' + fid + '>td.folder-contents-cell>.folder-expander');
          if(!expander.hasClass('expanded')){
            expander.click();
          }
          $(document).data('sCourseMaterialsFoldersActionPush', foldersActionPush);

          // The AJAX behavior of the expander will continue to
          // pop the sCourseMaterialsFolderActionPath array
        }
      });
    });

    // Handle any foldersexpanded as dicated by the hash
    if(location.hash.match('foldersexpanded')){
      var foldersExpanded = location.hash.split('foldersexpanded=')[1].split(',');

      foldersExpanded.forEach(function(currentValue){
          var fid = currentValue;
          var expander = $('#f-' + fid + '>td.folder-contents-cell>.folder-expander');
          if(!expander.hasClass('expanded')){
              expander.click();
          }
      });
    }
  }

  $('#s-generic-post-new-display-view:not(.sCourseMaterialsFolders-processed),#folder-contents-table:not(.sCourseMaterialsFolders-processed)', context).addClass('sCourseMaterialsFolders-processed').each(function() {
    var table = $(this);

    if(table.attr('id') == 'folder-contents-table'){
      // Add action link behavior
	    $('tr td.actions').sActionLinks({ hidden: false, wrapper: '.action-links-wrapper' });

      var addMaterialsActionLinks = $('.materials-top .course-content-action-links .action-links');
      var inlineAddLinksWrapper = $('<div id="course-materials-action-links-inline" class="hidden"></div>');
      $('body').append(inlineAddLinksWrapper);
      var lastMaterialsRowAddTarget = null;

      table.click(function(e){
        var target = $(e.target);

        // Add materials behavior
        // Since the add materials action links are outside the table,
        // find them in the global context
        if(target.parent('.materials-row-add-line').length){
          var materialsRowAddId = target.closest('.materials-row-add').attr('id');
          var materialsRowAddIdSplit = materialsRowAddId.split('-');
          var targetFid = materialsRowAddIdSplit[3];
          var targetWeight = materialsRowAddIdSplit[4];

          // clicking on the same line should close the menu
          if(lastMaterialsRowAddTarget && materialsRowAddId == lastMaterialsRowAddTarget.closest('.materials-row-add').attr('id')){
            inlineAddLinksWrapper.hide();
            lastMaterialsRowAddTarget = null;
            return;
          }

          lastMaterialsRowAddTarget = target;

          // Make sure that the links we copy are the most up to date ones
          // that contain any dynamic changes to the original menu
          var targetOffset = target.offset();
          inlineAddLinksWrapper.empty()
            .data('materialsRowAddId', materialsRowAddId)
            .append(addMaterialsActionLinks.clone(true).css('display', 'block'))
            .show()
            .css({
                position: 'absolute',
                top: targetOffset.top + target.height(),
              });
          if (document.dir === 'rtl') {
            inlineAddLinksWrapper.css({
                left: targetOffset.left + target.outerWidth()
              });
          }
          else {
            inlineAddLinksWrapper.css({
                left: targetOffset.left
              });
          }

          // Modify the links to reflect the proper folder and weight
          $('li', inlineAddLinksWrapper).each(function(){
            var actionItem = $(this);
            var actionLink = $('a', actionItem);
            var actionItemClass = actionItem.attr('class');

            //Some items, like the separator lines, don't contain links. Skip them.
            if(actionLink[0] == undefined) {
              return true;
            }

            var pathname = actionLink[0].pathname;

            // IE doesn't return a leading slash for href paths,
            // but other browsers do. For consistency, strip it
            // here and add it back below.
            pathname = pathname.replace(/^\//,'');

            var queryString = actionLink[0].search;
            if(!queryString.length){
              var qsParsed = {};
            }
            else {
              var qsParsed = getQueryParams(queryString);
            }

            switch(actionItemClass){
              case 'action-import-library':
                if(targetFid > 0){
                  qsParsed.topic_nid = targetFid;
                }
                else {
                  delete qsParsed.topic_nid;
                }
                qsParsed.fweight = targetWeight;
                actionLink.attr('href', '/' + pathname + '?' + jQuery.param(qsParsed));
                break;

              case 'action-find-resources':
                // Don't show the action-find-resources
                actionItem.remove();
                break;

              default:
                var isUnderStudentChoice = target.parents('.material-row-student-choice').length > 0;
                if (isUnderStudentChoice && (actionItemClass === 'action-create-folder' || actionItemClass === 'action-create-student-choice')) {
                    actionItem.remove();
                    return;
                }
                if(targetFid == 0 && !sCourseMaterialsDisplayIsWithoutIndex()){
                  // Only allow folders on top level
                  if(actionItemClass != 'action-create-folder'){
                    actionItem.remove();
                    return;
                  }
                  else {
                    actionItem.addClass('folder-no-materials');
                  }
                }

                qsParsed.f = targetFid;
                qsParsed.fweight = targetWeight;
                actionLink.attr('href', '/' + pathname + '?' + jQuery.param(qsParsed));
                break;
            }
          });
        }
      });

      // Click-out behavior
      $('body').click(function(e){
        var target = $(e.target);
        if(target.parent('.materials-row-add-line').length == 0){
          inlineAddLinksWrapper.hide();
          lastMaterialsRowAddTarget = null;
        }
      });
    }

    $('.has-view-rule:not(.completed)', table).click(function(){
    	var parent = $(this).parents('.type-document:first');
    	var nid = parent.attr('id').split('-')[1];
    	$.ajaxSecure({
    		url: '/course/materials/' + nid + '/view_completion'
    	});
    });
  });

  $('#closeable-message-s_course_find_resources:not(.sCourseMaterialsFolders-processed)', context).addClass('sCourseMaterialsFolders-processed').each(function(){
	  $(document).bind('s_common_closeable_message_closed', function(e, mesID){
		 if(mesID == 's_course_find_resources'){
			 var fakeCluetip = '<div class="fake-cluetip"><span class="arrow-top"><span>' + Drupal.t('You can find resources for your course in this menu.') + '</div>';
			 var offset = $('.course-content-action-links').offset();
			 $('body').append(fakeCluetip);
			 $('.fake-cluetip').css({'position': 'absolute' , 'left': offset.left + $('.course-content-action-links').width() , 'top': offset.top });
			 setTimeout(function(){
				 $('.fake-cluetip').remove();
			 }, 2000);
		 }
	  });
  });

  $('#s-course-materials-folder-create-form:not(.sCourseMaterialsFolders-processed)', context).addClass('sCourseMaterialsFolders-processed').each(function(){
    var form = $(this);

    var warningMsg = $('.rules-msg', form); //warning for completion rules removal if selected item has rule on it
    var startWrapper = $('.availability-start-wrapper', form);
    var addEndLink = $('.availability-add-end', form);
    var endWrapper = $('.availability-end-wrapper', form);
    var applyChildrenWrapper = $('#edit-apply-to-children-wrapper', form);

    // Add end time
    addEndLink.click(function(){
      $(this).remove();
      endWrapper.show();
      sPopupsResizeCenter()
    });

    $('#edit-availability', form).bind('change', function(){
      var val = parseInt($(this).val());

      //show/hide relevant form fields depending on the chosen folder availability settings
      switch(val){
      	//visible
        case 1:
          applyChildrenWrapper.show();
          if(warningMsg.length){
            warningMsg.hide();
          }
          break;
        //hidden
        case 2:
          applyChildrenWrapper.hide();
          if(warningMsg.length){
            warningMsg.show();
          }
          break;
        //Available after...
        case 3:
          applyChildrenWrapper.hide();
          if(warningMsg.length){
            warningMsg.show();
          }
          break;
        //Available between...
        case 4:
          applyChildrenWrapper.hide();
          if(warningMsg.length){
            warningMsg.show();
          }
          addEndLink.remove();
          endWrapper.show();

          break;
        default:
          break;
      }

      sPopupsResizeCenter()
    });

    $('#edit-availability', form).trigger('change');
  });

  $('#s-course-materials-folder-completion-form:not(.sCourseMaterialsFolders-processed)', context ).addClass('sCourseMaterialsFolders-processed').each(function(){

    var form = $(this);
	  dueEventsMap = {};

      //bind click event on the html links to the hidden ahah submitters
      $('.add-rule', form).click(function(){
          if (!$(this).hasClass('disabled')){
            $('#edit-rules-submitter', form).trigger('click');
          }
      });

      $('.auto-populate', form).click(function(){
    	 $('.ahah-populate-submitter', form).trigger('click');
      });

      //bind javascript events for the existing rule fields
      sCourseMaterialsSetupRules(form, true, dueEventsMap);
      sCourseMaterialsSetupRemove('rule-option', form, dueEventsMap);

      $(document).ajaxSend(function(e, xhr, settings){
        //right before ajax request is sent add class to disable button until request is complete
        if(settings.url == '/course/new_rule'){
            $('.add-rule', form).addClass('disabled');
        }
      })
      //if ahah fields are produced, rebind the javascript events on the ahah fields
      $(document).ajaxComplete(function(e, xhr, settings){
    	  if(settings.url == '/course/new_rule' || settings.url == '/course/remove_rule' || settings.url == '/course/populate_rule'){
    		  sCourseMaterialsSetupRules(form, false, dueEventsMap, (settings.url == '/course/remove_rule'));
    		  sCourseMaterialsSetupRemove('rule-option', form, dueEventsMap);

    		  //hide the "add prerequisites" link if user made all folders sequential at the root level
    		  var addRule = $('.add-rule', form);
    		  if(settings.url == '/course/populate_rule'){
    			  addRule.hide();
    		  }
    		  //reshow the "add prerequisites" link if user removes one of the populated rules
    		  else if(settings.url == '/course/remove_rule' && !addRule.is(':visible')){
    			  addRule.show();
    		  }

    	    sCourseMaterialsHideDueEventsWarningIfNeeded(dueEventsMap, form);

    	    //free up button
    	    $('.add-rule', form).removeClass('disabled');
    	  }
    	  sPopupsResizeCenter();
      });
  });

}

/**
 * Setup the delete buttons next to the fields
 */
function sCourseMaterialsSetupRemove(parentClass, form, dueEventsMap){
    $('.' + parentClass + ':not(.sCourseMaterialsFolders-processed)', form).addClass('sCourseMaterialsFolders-processed').each(function(){
    	var parent = $(this);
    	$('.delete-btn', parent).click(function(){
    		var id = parent.attr('id');
    		var existing = parent.hasClass('existing') ? '1' : '0';
    		//record the rid of the deleted field and if the deleted field was na existing rule
    		$('.rule-remove-existing', form).val(existing);
    		$('.rule-remove-id', form).val(parseInt(id));
    		//remove from dueEventsMap
    		delete dueEventsMap[id];
    		//trigger the deletion
    		$('.ahah-remove-rule', form).click();
    	});
    });
}

/**
 * Setup form behavior for the rule fields
 */
function sCourseMaterialsSetupRules(form, existing, dueEventsMap, ahahCallback){
  if (typeof ahahCallback == 'undefined') {
    ahahCallback = false;
  }

  if (typeof Drupal.settings.s_course == 'undefined' || typeof Drupal.settings.s_course.type_options == 'undefined') {
    return;
  }

  var typeOptions = Drupal.settings.s_course.type_options;
  var types = Drupal.settings.s_course.types;
  var maxPts = Drupal.settings.s_course.max_pts;
  var constants = Drupal.settings.s_course.constants; //the numerical constant which corresponds to the "must score at least" rule
  var dueEvents = Drupal.settings.s_course.due_events;
  var commentsDisabled = Drupal.settings.s_course.comments_disabled;
  var submitDisabled = Drupal.settings.s_course.submit_disabled;

	$('.rule-item:not(.sCourseMaterialsFolders-processed)', form).addClass('sCourseMaterialsFolders-processed').each(function(){
  	var itemField = $(this);
  	var ruleContext = itemField.parents('.rule-option:first');
  	var id = ruleContext.attr('id');
  	var firstChange = true;

  	//bind events when the object field of the rule is changed
  	itemField.change(function(e){
    	var item = itemField.val();
    	var ruleAction = $('.rule-action', ruleContext);
    	var itemType = types[item];
    	if(item in dueEvents && dueEvents[item] > 0){
    		$('.has-due-event-warning', form).show();
    		dueEventsMap[id] = id;
    	}

      sCourseMaterialsHideDueEventsWarningIfNeeded(dueEventsMap, form);

    	//hide and/or show options that are allowed for the current type
    	var selected = $('option:selected', ruleAction).val();
    	ruleAction.empty();
    	$('.action-options option').each(function(){
    		var option = $(this);
    		var action = option.val();
    		//skip the comment rule if comment is disabled
    		if(action == constants.comment && commentsDisabled[item] == true){
    			return true;
    		}
    		//skip the submit/score at least rule if submit (eg. dropbox) is disabled
    		if((action == constants.submit || action == constants.score) && submitDisabled[item] == true){
    			return true;
    		}
    		if($.inArray(parseInt(action), typeOptions[itemType]) > -1){
    			var clonedOption = option.clone().appendTo(ruleAction);
    			if(clonedOption.val() == selected){
    				clonedOption.attr('selected', 'selected');
    			}
    		}
    	});

    	//reset action field to the first option
    	if((!firstChange || !existing) && !ahahCallback){
    		ruleAction.val($('option:visible:first', ruleAction).val());
    	}
    	else{
    		firstChange = false;
    	}

    	//hide the max points field
    	$('.max-pt', ruleContext).hide();
    	//change rule icon to current content type
    	$('.rule-icon', ruleContext).html(Drupal.settings.s_course.rule_icons[itemField.val()]);
    	sPopupsResizeCenter();
  	});

  	//fire event for first time display
  	itemField.change();
  });

	$('.rule-action:not(.sCourseMaterialsFolders-processed)', form).addClass('sCourseMaterialsFolders-processed').each(function(){
		var actionField = $(this);
		var ruleContext = actionField.parents('.rule-option:first');

		//bind events when the action field of the rule is changed
		actionField.change(function(){
			var item = $('.rule-item', ruleContext).val();
      	if(actionField.val() == constants.score){
      		//if the action is to "score at least" modify maxpts to correspond to the current item's max points
      		$('.max-pt-num', ruleContext).html(maxPts[item]);
      		$('.max-pt', ruleContext).show();
      	}
      	else{
      		$('.max-pt', ruleContext).hide();
      	}
      	sPopupsResizeCenter();
		});

		//fire event for first time display
		actionField.change();
	});
}

function sCourseMaterialsHideDueEventsWarningIfNeeded(dueEventsMap, form) {
  if(!Object.keys(dueEventsMap).length){
    $('.has-due-event-warning', form).hide();
  }
}
