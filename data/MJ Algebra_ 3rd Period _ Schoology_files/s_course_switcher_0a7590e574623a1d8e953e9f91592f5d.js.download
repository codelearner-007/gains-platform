Drupal.behaviors.sCourseSwitcher = function(context){
  $('#taught-courses-switcher #edit-course-switcher-select-nid:not(.sCourseSwitcher-processed)',context).addClass('sCourseSwitcher-processed').each(function(){
    var switchObj = $(this);

    // in the gradebook we want to not change the selector because of our onbeforeunload event.
    if($('body.s-gradebook').length > 0) {
      switchObj.selectmenu({
        change: function(){
          switchObj.selectmenu('value', originalSelected);
        }
      });

      var originalSelected = switchObj.selectmenu('value');
    }
    else {
      switchObj.selectmenu();
    }

    switchObj.change(function(e){
      var path = window.location.pathname;
      var pathSplit = path.split('/');
      pathSplit[2] = $(this).val();
      setTimeout(function(){
	      	window.location.href = pathSplit.join('/');
      }, 500);
      $(this).val(0);
    });
  });

 // ng-init="active=false" ng-class="{\'ui-state-active\': active}" ng-click="active=!active; load();"
  $('#taught-courses-switcher #edit-course-switcher-select-nid-button:not(.sCourseSwitcher-processed)',context).addClass('sCourseSwitcher-processed').each(function(){
    var KEY_ESCAPE = 27;
    var KEY_TAB = 9;
    var KEY_ARROW_UP = 38;
    var KEY_ARROW_DOWN = 40;

    var switchBtn = $(this),
        switcherContainer = switchBtn.siblings('.s-course-course-switcher');

    function closeSwitcher() {
      switchBtn.removeClass('ui-state-active').attr('aria-expanded', 'false');
      getSwitcherList().removeClass('ui-selectmenu-open');
    }

    // Re-query the DOM each time to handle the Angular template loading asynchronously
    function getSwitcherList() {
      return switcherContainer.find('#edit-course-switcher-select-nid-menu');
    }

    function getVisibleMenuItems() {
      return getSwitcherList().find('a[role="menuitem"]:visible');
    }

    switchBtn.click(function(e){
      e.preventDefault();
      switchBtn.toggleClass('ui-state-active');
      if(switchBtn.hasClass('ui-state-active')){
        switchBtn.attr('aria-expanded', 'true');
        getSwitcherList().addClass('ui-selectmenu-open');
        sAngular.contextExec(getSwitcherList());
        setTimeout(function() {
          var $firstItem = getVisibleMenuItems().first();
          if ($firstItem.length) $firstItem.focus();
        }, 0);
      }
      else{
        closeSwitcher();
      }
    });

    switchBtn.add(switcherContainer).on('keydown.sCourseSwitcher', function(e) {
      var key = e.keyCode || e.which;
      if (!switchBtn.hasClass('ui-state-active')) return;

      if (key === KEY_ESCAPE) {
        e.preventDefault();
        e.stopPropagation();
        closeSwitcher();
        switchBtn.focus();
      } else if (key === KEY_TAB) {
        // Navigate through dropdown items with Tab/Shift+Tab instead of closing immediately
        var $items = getVisibleMenuItems();
        if (!$items.length) {
          closeSwitcher();
          return;
        }
        var idx = $items.index(e.target);
        if (e.shiftKey) {
          // Shift+Tab: move to previous item, close if already on first item
          if (idx <= 0) {
            closeSwitcher();
            switchBtn.focus();
            e.preventDefault();
          } else {
            e.preventDefault();
            $items.eq(idx - 1).focus();
          }
        } else {
          // Tab: move to next item, close if already on last item
          if (idx >= $items.length - 1) {
            closeSwitcher();
          } else {
            e.preventDefault();
            $items.eq(idx + 1).focus();
          }
        }
      } else if (key === KEY_ARROW_DOWN || key === KEY_ARROW_UP) {
        e.preventDefault();
        var $items = getVisibleMenuItems();
        if (!$items.length) return;
        var idx = $items.index(e.target);
        var nextIdx = (key === KEY_ARROW_DOWN)
          ? (idx + 1) % $items.length
          : (idx - 1 + $items.length) % $items.length;
        $items.eq(nextIdx).focus();
      }
    });

    $(document).unbind('click.s_course_course_switcher').bind('click.s_course_course_switcher', function(e){
      if(!$(e.target).closest('#taught-courses-switcher').length){
        closeSwitcher();
      }
    });
  });
}