param([switch]$ConfigureDemo)
$ErrorActionPreference='Stop'
Push-Location (Split-Path -Parent $PSScriptRoot)
function Invoke-LabDocker { param([string[]]$Arguments) & docker @Arguments; if($LASTEXITCODE -ne 0){throw 'Docker operation failed'} }
try {
    Invoke-LabDocker @('compose','cp','wordpress/biurko-lab','wordpress:/var/www/html/wp-content/themes/biurko-lab')
    Invoke-LabDocker @('compose','cp','wordpress/mu-plugins','wordpress:/var/www/html/wp-content/mu-plugins')
    if($ConfigureDemo) {
        Invoke-LabDocker @('compose','cp','assets','wordpress:/tmp/lab-assets')
        Invoke-LabDocker @('compose','cp','scripts/setup-store.php','wordpress:/tmp/lab-setup.php')
        Invoke-LabDocker @('compose','exec','-T','wordpress','php','/tmp/lab-setup.php')
        Invoke-LabDocker @('compose','cp','wordpress:/tmp/lab-media.json','data/media.local.json')
    }
    Invoke-LabDocker @('compose','cp','wordpress/htaccess.local','wordpress:/var/www/html/.htaccess')
} finally { Pop-Location }
