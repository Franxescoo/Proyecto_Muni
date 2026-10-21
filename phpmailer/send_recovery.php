<?php

declare(strict_types=1);

require __DIR__ . '/vendor/autoload.php';

use PHPMailer\PHPMailer\Exception;
use PHPMailer\PHPMailer\PHPMailer;

$payload = json_decode(stream_get_contents(STDIN), true);
if (!is_array($payload)) {
    fwrite(STDERR, "Invalid JSON input.\n");
    exit(2);
}

foreach (['to', 'subject', 'text', 'html'] as $field) {
    if (!isset($payload[$field]) || !is_string($payload[$field])) {
        fwrite(STDERR, "Missing mail field: {$field}.\n");
        exit(2);
    }
}

$requiredEnvironment = [
    'EMAIL_HOST',
    'EMAIL_PORT',
    'EMAIL_HOST_USER',
    'EMAIL_HOST_PASSWORD',
    'DEFAULT_FROM_EMAIL',
];
foreach ($requiredEnvironment as $name) {
    if (getenv($name) === false || getenv($name) === '') {
        fwrite(STDERR, "Missing mail environment variable: {$name}.\n");
        exit(2);
    }
}

$mailer = new PHPMailer(true);
try {
    $mailer->isSMTP();
    $mailer->Host = getenv('EMAIL_HOST');
    $mailer->Port = (int) getenv('EMAIL_PORT');
    $mailer->SMTPAuth = true;
    $mailer->Username = getenv('EMAIL_HOST_USER');
    $mailer->Password = getenv('EMAIL_HOST_PASSWORD');
    $mailer->SMTPSecure = getenv('EMAIL_USE_SSL') === 'True'
        ? PHPMailer::ENCRYPTION_SMTPS
        : PHPMailer::ENCRYPTION_STARTTLS;
    $mailer->CharSet = 'UTF-8';
    $mailer->setFrom(getenv('DEFAULT_FROM_EMAIL'), 'Municipalidad de La Serena');
    $mailer->addAddress($payload['to']);
    $mailer->Subject = $payload['subject'];
    $mailer->Body = $payload['html'];
    $mailer->AltBody = $payload['text'];
    $mailer->isHTML(true);
    $mailer->send();
} catch (Exception $exception) {
    fwrite(STDERR, "PHPMailer send failed: {$exception->getMessage()}\n");
    exit(1);
}
