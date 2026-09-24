*** Settings ***
Documentation    Test cases for github-user-stats snap
Resource         kvm.resource


*** Test Cases ***
Github User Stats Launches And Renders
    [Documentation]    Verify github-user-stats snap launches and renders a UI on Mir
    [Tags]    smoke    yarf:certification_status: blocker
    Log Screenshot
